#!/usr/bin/python3
import csv
import os
import requests
import statistics
import sys
import tabulate
import tsv

from catalog.catalog import Item

BROKER_RATE = 0.05
REPROCESSING_EFFICIENCY = 0.5
REPROCESSING_TAX_RATE = 0.05
SALES_TAX_RATE = 0.05

ESI_MARKET_HISTORY_URI = "https://esi.evetech.net/latest/markets/{regionId}/history/?datasource=tranquility&type_id={typeId}"
esiSession = requests.Session()

def getJsonFromEsi(dataMap):
    uri = ESI_MARKET_HISTORY_URI.format_map(dataMap)
    r = esiSession.get(uri)
    if 200 != r.status_code:
        raise ValueError("Non-200 error code {} from ESI for {}".format(r.status_code, uri))

    return r.json()

def getFiveDayAverage(data):
    return statistics.mean(map(lambda priceDict: priceDict["average"], data[-5:]))

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

items = []
with open(os.path.dirname(os.path.abspath(__file__)) + os.path.sep + "invTypes.csv") as csvFile:
    csvReader = csv.DictReader(csvFile)
    for row in csvReader:
        try:
            typeId = int(row["typeID"])
        except ValueError:
            continue
        items.append(Item(typeId=typeId, enUsName=row["typeName"], portionSize=int(row["portionSize"])))

typeIdToItem = {item.typeId: item for item in items}
nameToItem = {item.name: item for item in items}

outputCount = {}
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

        try:
            outputCount[materialTypeId] += 1
        except KeyError:
            outputCount[materialTypeId] = 1

reprocessOutputsToConsider = list(map(lambda tuple: tuple[0], filter(lambda tuple: tuple[1] > 200, outputCount.items())))

inventory = {}
invReader = tsv.TsvReader(sys.stdin)
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
    # "Amarr": {
    #     "regionId": 10000043,
    # },
    # "Dodixie": {
    #     "regionId": 10000032,
    # },
}

regionIdMap = {v["regionId"]: k for k, v in regionMap.items()}

eveMarketerUriBase = "https://api.evemarketer.com/ec/marketstat/json?typeid={}&regionlimit={}"

offers = {}
jitaOffers = {}
for region in regionMap:
    regionId = regionMap[region]["regionId"]

    for typeId in inventory.keys():
        item = typeIdToItem[typeId]
        response = getJsonFromEsi({
            "regionId": regionId,
            "typeId": typeId
        })
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
    response = getJsonFromEsi({
        "regionId": regionMap["Jita"]["regionId"],
        "typeId": typeId
    })
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


bestOffers = {k: [] for k in regionMap.keys()}
for typeId in offers:
    bestRegion = ""
    bestPrice = -1.00

    for region in offers[typeId]:
        currentPrice = offers[typeId][region]["price"]
        if currentPrice > bestPrice:
            bestRegion = region
            bestPrice = currentPrice

    bestOffers[bestRegion].append(offers[typeId][bestRegion])

for region in bestOffers:
    regionOffers = bestOffers[region]
    if 0 == len(regionOffers):
        continue

    print(region)

    doJitaComparison = "Jita" != region

    table = ["Item Name", "Unit Price"]
    if doJitaComparison:
        table.append("Jita")

    table.append("Reprocess Value")
    table.append("Qty")
    table.append("Estimated Price")
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

    print(tabulate.tabulate(tableData, table, tablefmt="github", floatfmt=",.2f"))
    print()
