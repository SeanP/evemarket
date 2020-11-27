#!/usr/bin/python3
import asyncio
import csv
import httpx
import json
import os
import statistics
import sys
import tabulate
import time
import tsv

from catalog.catalog import Item

BROKER_RATE = 0.05
REPROCESSING_EFFICIENCY = 0.5
REPROCESSING_TAX_RATE = 0.05
SALES_TAX_RATE = 0.05

ESI_MARKET_HISTORY_URI = "https://esi.evetech.net/latest/markets/{regionId}/history/?datasource=tranquility&type_id={typeId}"

regionMap = {
    "Jita": {
        "regionId": 10000002,
    },
    "Rens": {
        "regionId": 10000030,
    },
    "Hek": {
        "regionId": 10000042,
    },
    "Amarr": {
        "regionId": 10000043,
    },
    "Dodixie": {
        "regionId": 10000032,
    },
}

items = []
nameToItem = {}
typeIdToItem = {}

def initializeItems():
    start = time.time()
    if 0 < len(items):
        return
    with open(os.path.dirname(os.path.abspath(__file__)) + os.path.sep + "invTypes.csv") as csvFile:
        csvReader = csv.DictReader(csvFile)
        for row in csvReader:
            try:
                typeId = int(row["typeID"])
            except ValueError:
                continue
            items.append(Item(typeId=typeId, enUsName=row["typeName"], portionSize=int(row["portionSize"])))

    for item in items:
        typeIdToItem[item.typeId] = item
        nameToItem[item.name] = item

    with open(os.path.dirname(os.path.abspath(__file__)) + os.path.sep + "invTypeMaterials.csv") as csvFile:
        csvReader = csv.DictReader(csvFile)
        for row in csvReader:
            try:
                typeId = int(row["typeID"])
                materialTypeId = int(row["materialTypeID"])
                quantity = int(row["quantity"])
            except ValueError:
                continue

            typeIdToItem[typeId].addReprocessingOutputs(materialTypeId, quantity)

    print("Init SDE time: {:.3f} s".format(time.time() - start))

async def getJsonFromEsi(client, regionId, typeId, orderHistory):
    uri = ESI_MARKET_HISTORY_URI.format_map({
        "regionId": regionId,
        "typeId": typeId
    })
    r = await client.get(uri)
    if 200 != r.status_code:
        raise ValueError("Non-200 error code {} from ESI for {}".format(r.status_code, uri))

    orderHistory[regionId][typeId] = r.json()

def runBatch(requestMap):
    orderHistory = {}
    client = httpx.AsyncClient()
    loop = asyncio.get_event_loop()
    tasks = []
    for regionId in requestMap.keys():
        orderHistory[regionId] = {}
        for typeId in requestMap[regionId]:
            tasks.append(loop.create_task(getJsonFromEsi(client=client, regionId=regionId, typeId=typeId, orderHistory=orderHistory)))
    tasks.append(loop.create_task(client.aclose()))
    loop.run_until_complete(asyncio.wait(tasks))
    return orderHistory

def getFiveDayAverage(data):
    return statistics.mean(map(lambda priceDict: priceDict["average"], data[-5:]))

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def doTheThing(inputStream, regionsToCheck=["Jita", "Hek", "Rens"]):
    initializeItems()

    inventory = {}
    invReader = tsv.TsvReader(inputStream)
    for rawRow in invReader:
        row = list(rawRow)
        item = nameToItem[row[0]]
        quantity = int(row[1].replace(",", ""))
        if item.typeId not in inventory:
            inventory[item.typeId] = {
                "quantity": quantity,
                "item": item
            }
        else:
            inventory[item.typeId]["quantity"] += quantity

    reprocessOutputsToConsider = set()

    for invItem in inventory.values():
        for materialTypeId in invItem["item"].reprocessingOutputs.keys():
            reprocessOutputsToConsider.add(materialTypeId)

    # Prefetch everything
    requestMap = {}
    for materialTypeId in reprocessOutputsToConsider:
        jitaRegion = regionMap["Jita"]["regionId"]
        try:
            requestMap[jitaRegion].add(materialTypeId)
        except KeyError:
            requestMap[jitaRegion] = {materialTypeId}

    # for regionId in map(lambda region: region["regionId"], regionMap.values()):
    for regionId in map(lambda region: regionMap[region]["regionId"], regionsToCheck):
        for itemId in inventory.keys():
            try:
                requestMap[regionId].add(itemId)
            except KeyError:
                requestMap[regionId] = {itemId}

    start = time.time()
    orderHistory = runBatch(requestMap)
    print("Offer retrieval time: {}".format(time.time() - start))

    offers = {}
    jitaOffers = {}
    for region in regionsToCheck:
        regionId = regionMap[region]["regionId"]

        for typeId in inventory.keys():
            item = typeIdToItem[typeId]
            response = orderHistory[regionId][typeId]
            try:
                fiveDayAverage = getFiveDayAverage(response)
            except statistics.StatisticsError:
                eprint("Failed to process '{typeId}' in {region}. Continuing.".format_map({
                    "typeId": item.name,
                    "region": region
                }))
                continue

            if typeId not in offers:
                offers[typeId] = {}

            offers[typeId][region] = {
                "item": item,
                "price": fiveDayAverage,
            }

            if "Jita" == region:
                jitaOffers[typeId] = fiveDayAverage

    reprocessPrices = {}

    for typeId in reprocessOutputsToConsider:
        response = orderHistory[regionMap["Jita"]["regionId"]][typeId]
        fiveDayAverage = getFiveDayAverage(response)
        reprocessPrices[typeId] = fiveDayAverage

    reprocessOffers = {}
    for typeId in inventory.keys():
        reprocessValue = 0
        item = typeIdToItem[typeId]
        if 0 == len(item.reprocessingOutputs):
            continue
        for materialTypeId in item.reprocessingOutputs.keys():
            try:
                unitPrice = reprocessPrices[materialTypeId]
            except KeyError:
                continue

            reprocessValue += (1 - REPROCESSING_TAX_RATE) * REPROCESSING_EFFICIENCY * unitPrice * item.reprocessingOutputs[materialTypeId]

        reprocessOffers[typeId] = reprocessValue


    bestOffers = {k: [] for k in regionsToCheck}
    for typeId in offers:
        bestRegion = ""
        bestPrice = -1.00

        for region in offers[typeId]:
            currentPrice = offers[typeId][region]["price"]
            if currentPrice > bestPrice:
                bestRegion = region
                bestPrice = currentPrice

        bestOffers[bestRegion].append(offers[typeId][bestRegion])

    results = {}
    for region in bestOffers:
        regionOffers = bestOffers[region]
        if 0 == len(regionOffers):
            continue

        doJitaComparison = "Jita" != region

        headers = ["Item Name", "Unit Price"]
        columnFormatString = ["{}", "{:,.2f}"]
        if doJitaComparison:
            headers.append("Jita")
            columnFormatString.append("{:,.2f} ISK")

        headers.append("Reprocess Value")
        columnFormatString.append("{:,.2f} ISK")
        headers.append("Qty")
        columnFormatString.append("{}")
        headers.append("Estimated Price")
        columnFormatString.append("{:,.2f} ISK")
        tableData = []
        for offer in regionOffers:
            item = offer["item"]
            typeId = item.typeId
            qty = inventory[typeId]["quantity"]
            unitPrice = offer["price"]
            row = [item.name, unitPrice]
            if doJitaComparison:
                row.append(jitaOffers[typeId])
            try:
                row.append(reprocessOffers[typeId])
            except KeyError:
                row.append(None)
            row.append(qty)
            row.append(qty * unitPrice)
            tableData.append(row)

        tableData.sort(key=lambda row: row[-1], reverse=True)

        results[region] = {
            'headers': headers,
            'data': tableData,
            'format': columnFormatString
        }
    return results


def main():
    results = doTheThing(sys.stdin)
    print(json.dumps(results))

if __name__ == "__main__":
    main()