from bottle import run, request, post, get
import json

@get('/')
def index():
    list = []
    out_file = open('/home/alex/IdeaProjects/untitled/myfile.json', 'w')
    with open('/home/alex/IdeaProjects/untitled/Data', 'r') as f:
        file = json.load(f)
    for value in file['object']:
        if value['Role'] == 'Editor':
            list.append(json.dumps(value))
    print(list)

run(host = 'localhost', port = 8080, debug = True)