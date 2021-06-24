from bottle import run, request, post, get
import pymongo
from bson import json_util


@get('/')
def index():
    # Connection to MongoDB
    myclient = pymongo.MongoClient("mongodb://localhost:27017/")
    mydb = myclient["CalendarDB"]
    Cal = mydb["Calendar"]
    Event = mydb["Events"]
    items = Cal.find({}, {'_id': 0, 'Events': 1})
    res = items[0]['Events']
    items_ev = Event.find({'_id': res}, {'Title': 1, 'Start': 1, 'End': 1})
    return json_util.dumps(items_ev)


run(host='0.0.0.0', port=12345, debug=True)
