from bottle import run, request, post, get
import json


@get('/')
def index():
    element = []
    with open('/home/alex/IdeaProjects/Server_JSON/Eventi.json', 'r') as f:
        file = json.load(f)
    #for value in file:
        #if value['Role'] == 'Editor':
        #element.append(json.dumps(value))
    return json.dumps(file)


run(host='0.0.0.0', port=12345, debug=True)
