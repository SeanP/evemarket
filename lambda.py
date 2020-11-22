import base64
import html
import json
import os
import urllib

from io import StringIO

import evemarket

USER_INVENTORY_FORM_FIELD = "user_inventory="

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

        if USER_INVENTORY_FORM_FIELD != inputForm[0:len(USER_INVENTORY_FORM_FIELD)]:
            raise ValueError("Input must include user inventory!")
        invInput = urllib.parse.unquote_plus(inputForm[len(USER_INVENTORY_FORM_FIELD):])

        body = '<h1>Results</h1>'
        tables = evemarket.doTheThing(StringIO(invInput))

        for region in tables.keys():
            table = tables[region]
            print(region)
            print(table["format"])
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
                print(row)
                body += '<tr>'
                for cellIdx in range(len(row)):
                    print(cellIdx)
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