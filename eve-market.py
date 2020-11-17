#!/usr/bin/python3
import csv
import os
import requests
import sys
import tabulate
import tsv

SALES_TAX_RATE = 0.05
BROKER_RATE = 0.05

typeIdToNameDict = {}
with open(os.path.dirname(os.path.abspath(__file__)) + os.path.sep + "invTypes.csv") as csvFile:
    csvReader = csv.DictReader(csvFile)
    for row in csvReader:
        try:
            typeId = int(row["typeID"])
        except ValueError:
            continue
        typeIdToNameDict[typeId] = row["typeName"]

nameToTypeIdDict = {v: k for k, v in typeIdToNameDict.items()}

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

offers = {}
jitaOffers = {}
for region in regionMap:
    regionId = regionMap[region]["regionId"]
    itemIdsToQuery = ",".join(list(map(lambda invItem: str(inventory[invItem]["typeId"]), inventory)))
    uri = "https://api.evemarketer.com/ec/marketstat/json?typeid={}&regionlimit={}".format(itemIdsToQuery, regionId)

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

bestOffers = {k: [] for k in regionMap.keys()}
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
        row.append(qty)
        row.append(qty * unitPrice)
        tableData.append(row)

    tableData.sort(key=lambda row: row[-1], reverse=True)
    # table.append(list(sorted(tableData, key=lambda row: row[4])))

    print(tabulate.tabulate(tableData, table, tablefmt="github", floatfmt=",.2f"))
    print()
