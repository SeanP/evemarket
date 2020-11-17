#!/usr/bin/python3
import csv
import os
import requests
import sys
import tabulate
import tsv

BROKER_RATE = 0.05
REPROCESSING_EFFICIENCY = 0.5
REPROCESSING_TAX_RATE = 0.05
SALES_TAX_RATE = 0.05

typeIdToNameDict = {}
typeIdProperties = {}
with open(os.path.dirname(os.path.abspath(__file__)) + os.path.sep + "invTypes.csv") as csvFile:
    csvReader = csv.DictReader(csvFile)
    for row in csvReader:
        try:
            typeId = int(row["typeID"])
        except ValueError:
            continue
        typeIdToNameDict[typeId] = row["typeName"]
        typeIdProperties[typeId] = {
            "typeName": row["typeName"],
            "portionSize": int(row["portionSize"]),
        }

nameToTypeIdDict = {v: k for k, v in typeIdToNameDict.items()}

reprocessingOutputs = {}
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

        if typeId not in reprocessingOutputs:
            reprocessingOutputs[typeId] = {}
        reprocessingOutputs[typeId][materialTypeId] = quantity / typeIdProperties[typeId]["portionSize"]

        try:
            outputCount[materialTypeId] += 1
        except KeyError:
            outputCount[materialTypeId] = 1

reprocessOutputsToConsider = list(map(lambda tuple: str(tuple[0]), filter(lambda tuple: tuple[1] > 200, outputCount.items())))

inventory = {}
invReader = tsv.TsvReader(sys.stdin)
for rawRow in invReader:
    row = list(rawRow)
    typeId = nameToTypeIdDict[row[0]]
    inventory[typeId] = {
        "typeId": nameToTypeIdDict[row[0]],
        "quantity": int(row[1])
    }

if len(inventory) > 200:
    raise ValueError("Inventory size of {} is more than 200. Reduce input size or implement batching.".format(len(inventory)))

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
    itemIdsToQuery = ",".join(list(map(lambda invItem: str(inventory[invItem]["typeId"]), inventory)))
    uri = eveMarketerUriBase.format(itemIdsToQuery, regionId)

    r = requests.get(uri)
    if r.status_code != 200:
        raise ValueError("Non-200 error code {} for {}".format(r.status_code, region))

    response = r.json()

    for offerPair in response:
        buy = offerPair["buy"]
        sell = offerPair["sell"]
        typeId = int(buy["forQuery"]["types"][0])
        if typeId not in offers:
            offers[typeId] = {}

        rawBuyPrice = buy["fivePercent"]
        adjustedBuyPrice = rawBuyPrice * (1 - SALES_TAX_RATE)
        rawSellPrice = sell["fivePercent"]
        adjustedSellPrice = rawSellPrice * (1 - BROKER_RATE - SALES_TAX_RATE)

        del buy["forQuery"]
        del sell["forQuery"]
        buy["typeId"] = typeId
        sell["typeId"] = typeId

        acceptedRegionOffer = {}
        if adjustedSellPrice > adjustedBuyPrice:
            acceptedRegionOffer = sell
            acceptedRegionOffer["offerType"] = "Sell"
        else:
            acceptedRegionOffer = buy
            acceptedRegionOffer["offerType"] = "Buy"

        offers[typeId][region] = acceptedRegionOffer

        if "Jita" == region:
            jitaOffers[typeId] = {
                "buy": buy,
                "sell": sell
            }

reprocessUri = eveMarketerUriBase.format(",".join(reprocessOutputsToConsider), regionMap["Jita"]["regionId"])
r = requests.get(reprocessUri)
if r.status_code != 200:
    raise ValueError("Non-200 error code {} for Jita Reprocessing".format(r.status_code))

response = r.json()

reprocessPrices = {}
for offerPair in response:
    buy = offerPair["buy"]
    sell = offerPair["sell"]
    typeId = int(buy["forQuery"]["types"][0])

    averagePrice = 0.5 * buy["fivePercent"] + 0.5 * sell["fivePercent"]

    reprocessPrices[typeId] = averagePrice

reprocessOffers = {}
for typeId in inventory.keys():
    reprocessValue = 0
    if typeId not in reprocessingOutputs:
        continue
    for materialTypeId in reprocessingOutputs[typeId].keys():
        try:
            unitPrice = reprocessPrices[materialTypeId]
        except KeyError:
            continue

        reprocessValue += (1 - REPROCESSING_TAX_RATE) * REPROCESSING_EFFICIENCY * unitPrice * reprocessingOutputs[typeId][materialTypeId]

    reprocessOffers[typeId] = reprocessValue
    # offers[typeId] = {
    #     "fivePercent": reprocessValue,
    #     "offerType": "Reprocess",
    #     "typeId": typeId,
    # }

bestOffers = {k: [] for k in regionMap.keys()}
# bestOffers["Reprocess"] = []
for offer in offers:
    bestRegion = ""
    bestPrice = -1.00

    for region in offers[offer]:
        currentPrice = offers[offer][region]["fivePercent"]
        if currentPrice > bestPrice:
            bestRegion = region
            bestPrice = currentPrice

    bestOffers[bestRegion].append(offers[offer][bestRegion])

for region in bestOffers:
    regionOffers = bestOffers[region]
    if 0 == len(regionOffers):
        continue

    print(region)

    doJitaComparison = "Jita" != region

    table = ["Item Name", "Sell Type", "Unit Price"]
    if doJitaComparison:
        table.append("Jita Buy")
        table.append("Jita Sell")

    table.append("Reprocess Value")
    table.append("Qty")
    table.append("Estimated Price")
    tableData = []
    for offer in regionOffers:
        typeId = offer["typeId"]
        qty = inventory[typeId]["quantity"]
        unitPrice = offer["fivePercent"]
        row = [typeIdToNameDict[offer["typeId"]], offer["offerType"], unitPrice]
        if doJitaComparison:
            row.append(jitaOffers[typeId]["buy"]["fivePercent"])
            row.append(jitaOffers[typeId]["sell"]["fivePercent"])
        try:
            row.append(reprocessOffers[typeId])
        except KeyError:
            row.append(None)
        row.append(qty)
        row.append(qty * unitPrice)
        tableData.append(row)

    tableData.sort(key=lambda row: row[-1], reverse=True)
    # table.append(list(sorted(tableData, key=lambda row: row[4])))

    print(tabulate.tabulate(tableData, table, tablefmt="github", floatfmt=",.2f"))
    print()
