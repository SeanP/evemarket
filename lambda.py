#!/usr/bin/python3
import base64
import html
import json
import os
import urllib

from io import StringIO

import evemarket

USER_INVENTORY_FORM_FIELD = "user_inventory"

with (open(os.path.dirname(os.path.abspath(__file__)) + os.path.sep + 'resources/header.html', 'r')) as file:
    htmlHeadPart = file.read().replace('\n', '')

with (open(os.path.dirname(os.path.abspath(__file__)) + os.path.sep + 'resources/footer.html', 'r')) as file:
    htmlFootPart = file.read().replace('\n', '')

with (open(os.path.dirname(os.path.abspath(__file__)) + os.path.sep + 'resources/inputBeforeContent.html', 'r')) as file:
    htmlInputBeforeContentPart = file.read().replace('\n', '')

with (open(os.path.dirname(os.path.abspath(__file__)) + os.path.sep + 'resources/inputAfterContent.html', 'r')) as file:
    htmlInputAfterContentPart = file.read().replace('\n', '')

def enact(event, context):
    invInput = ""
    if "POST" == event["requestContext"]["http"]["method"]:
        inputForm = base64.b64decode(event["body"]).decode("utf-8")

        inputs = {i[0]: i[1] for i in urllib.parse.parse_qsl(inputForm)}

        if USER_INVENTORY_FORM_FIELD not in inputs:
            raise ValueError("Input must include user inventory!")
        invInput = urllib.parse.unquote_plus(inputs[USER_INVENTORY_FORM_FIELD])
        del inputs[USER_INVENTORY_FORM_FIELD]

        body = '<h1>Results</h1>'
        tables = evemarket.doTheThing(StringIO(invInput), [region for region in inputs.keys()])

        for region in tables.keys():
            table = tables[region]
            body +='<h2>{}</h2>'.format(region)
            body += '<table class="table table-striped">'
            body += '<thead class="thead-dark">'
            body += '<tr>'
            for header in table["headers"]:
                body += '<th scope="col">{}</th>'.format(header)
            body += '</tr>'
            body += '</thead>'
            body += '<tbody>'
            for row in table["data"]:
                body += '<tr>'
                for cellIdx in range(len(row)):
                    body += '<td>'
                    if None != row[cellIdx]:
                        body += table["format"][cellIdx].format(row[cellIdx])
                    body += '</td>'
                body += '</tr>'
            body += '</tbody>'
            body += '</table>'
    else:
        body = ""

    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'text/html; charset=UTF-8'
        },
        'body': htmlHeadPart + htmlInputBeforeContentPart + invInput + htmlInputAfterContentPart + body + htmlFootPart
    }

if __name__ == "__main__":
    print(enact({
        "requestContext": {
            "http": {
                "method": "POST"
            }
        },
        "body": base64.b64encode("user_inventory=Imperial+Navy+Major+Insignia+I%093%09Empire+Insignia+Drops%09%09%090.30+m3%091%2C365%2C203.25+ISK%0D%0AMedium+%27Notos%27+Explosive+Charge+I%091%09Smart+Bomb%09%09High%0910+m3%09606%2C767.07+ISK%0D%0AArbalest+Compact+Light+Missile+Launcher%091%09Missile+Launcher+Light%09%09High%095+m3%09492%2C575.28+ISK%0D%0AContaminated+Nanite+Compound%094%09Salvaged+Materials%09%09%090.04+m3%09452%2C360.48+ISK%0D%0AArmor+Plates%098%09Salvaged+Materials%09%09%090.08+m3%09292%2C135.20+ISK%0D%0ACaldari+Navy+Commodore+Insignia+II%092%09Empire+Insignia+Drops%09%09%090.20+m3%09223%2C288.14+ISK%0D%0AMedium+I-b+Polarized+Structural+Regenerator%091%09Hull+Repair+Unit%09%09Medium%0910+m3%09169%2C246.33+ISK%0D%0AImperial+Navy+Colonel+Insignia+I%091%09Empire+Insignia+Drops%09%09%090.10+m3%09165%2C209.76+ISK%0D%0AMetal+Scraps%0974%09Commodities%09%09%090.74+m3%09155%2C807.00+ISK%0D%0APraetor+I%091%09Combat+Drone%09%09%0925+m3%09150%2C400.95+ISK%0D%0AAE-K+Compact+Drone+Damage+Amplifier%092%09Drone+Damage+Modules%09%09Low%0910+m3%09126%2C485.84+ISK&Jita=Jita&Amarr=Amarr&Dodixie=Dodixie&Hek=Hek&Rens=Rens".encode("utf-8"))
    }, {})["body"])