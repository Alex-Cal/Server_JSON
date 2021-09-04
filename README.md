# Server_JSON 
You must create a MongoDB DB named "CalendarDB" with the following collections (MongoDB version: 3.6.8):
- "Admin_auth"
- "Authorization"
- "Calendar"
- "Events"
- "Group"
- "Hier"
- "Temporal Pre-Condition"
- "User"

In the "Utility" folder, you'll find all the utilities needed to run the services exposed in "Server.py".
Python version: 3.8

Required libs:
- NetworkX
- Bottle
- Bottle_cors_plugin
- Bson
- Matplotlib

To expose the services on the "12345" port, on all addresses, run Server.py 
