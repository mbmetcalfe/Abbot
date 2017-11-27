#!/usr/local/bin/python3.6

from xml.dom.minidom import parse
import xml.dom.minidom
from xml.dom.minidom import getDOMImplementation

from pathlib import Path
from event import EventParticipant, Event, JSONtoObject, json2obj

# look here: https://wiki.python.org/moin/MiniDom
# DOM documentation: https://docs.python.org/3/library/xml.dom.html

def replaceText(node, newText):
    if node.firstChild.nodeType != node.TEXT_NODE:
        raise Exception("node does not contain text")

    node.firstChild.replaceWholeText(newText)

def old_xml():
    # Open XML document using minidom parser
    DOMTree = xml.dom.minidom.parse("2017_Event.xml")
    event = DOMTree.documentElement
    if event.hasAttribute("year"):
        print("Root element : {0}".format(event.getAttribute("year")))

    # Get all the participants
    participants = event.getElementsByTagName("participant")

    # Print detail of each participant.
    for participant in participants:
        print("*****Participant*****")
        if participant.hasAttribute("name"):
            print("Name: {0}".format(participant.getAttribute("name")))
        if participant.hasAttribute("discord_id"):
            print("Discord Id: {0}".format(participant.getAttribute("discord_id")))

        address = participant.getElementsByTagName('address')[0]
        print("Address: {0}".format(address.childNodes[0].data))
        size = participant.getElementsByTagName('size')[0]
        print("Size: {0}".format(size.childNodes[0].data))
        #giftee = participant.getElementsByTagName('giftee')[0]
        giftee = participant.getElementsByTagName('giftee')

        if len(giftee) == 0:
            print("nothin'")
        else:
            giftee = participant.getElementsByTagName('giftee')[0]
##        if len(giftee.childNodes) == 0:
##            try:
##                # try to add a node and save the doc
##                replaceText(giftee, "Giftee in here.")
##            except:
##                print("Error saving")
##
        if giftee.hasChildNodes() and len(giftee.childNodes) > 0:
            print("Giftee: {0}".format(giftee.childNodes[0].data))

def getNodeText(rootNode, nodeName):
    rootNode.getElementsByTagName(nodeName)
    
def xml_event_status():
    doc = xml.dom.minidom.parse("2017_Event.xml");
    
    participants = doc.getElementsByTagName("participant")
    print("SECRET GIFTER EVENT EXTRAVAGANZA 2017\n%d Participants:" % participants.length)
    for participant in participants:
        print("Name: {0}; Discord Id: {1}; \n\tSize: {2};\n\tAddress: {3}".format(
            participant.getAttribute("name"),
            participant.getAttribute("discord_id"),
            participant.getElementsByTagName("size")[0].childNodes[0].data,
            participant.getElementsByTagName("address")[0].childNodes[0].data))
        giftee = participant.getElementsByTagName('giftee')
        if len(giftee) == 0: # no giftee tag yet, so add one
            print("\tGiftee: N/A.")
        else:
            print("\n\tGiftee: {0}.".format(giftee))
    
def main():
# use the parse() function to load and parse an XML file
   doc = xml.dom.minidom.parse("2017_Event.xml");
  
# print out the document node and the name of the first child tag
   print(doc.nodeName)
   print(doc.firstChild.tagName)
  
# get a list of XML tags from the document and print each one
   participants = doc.getElementsByTagName("participant")
   print("%d Participants:" % participants.length)
   for participant in participants:
     print("Name: {0}; Discord Id: {1}; \n\tSize: {2};\n\tAddress: {3}".format(
        participant.getAttribute("name"),
        participant.getAttribute("discord_id"),
        participant.getElementsByTagName("size")[0].childNodes[0].data,
        participant.getElementsByTagName("address")[0].childNodes[0].data))
     giftee = participant.getElementsByTagName('giftee')
     if len(giftee) == 0: # no giftee tag yet, so add one
         newGiftee = doc.createElement("giftee")
         newGifteeName = doc.createTextNode("Test")
         newGiftee.appendChild(newGifteeName)
         participant.appendChild(newGiftee)
     else:
         print("\tGiftee: {0}.".format(giftee))
   print(" ")

   fileHandle = open("./test.xml","w")
   doc.writexml(fileHandle)
   fileHandle.close()
    
def json_event_status():
    event2017 = Event('SECRET GIFTER EVENT EXTRAVAGANZA 2017')
    
    myself = EventParticipant('Michael', 12345)
    event2017.participants[12345] = myself
    
    event2017.participants[12345].name = 'Changed'
    
#    myselfJSON = json.dumps(myself, default=jsonDefault)
#    print(myselfJSON)
    
    eventJSON = json.dumps(event2017, default=jsonDefault)
    print(eventJSON)

def json_event_test():
    eventName = '2017'
    eventfile = Path("config/event_{0}.json".format(eventName))
    event2017 = Event(eventName, 4)
    
    try:
        participant = EventParticipant('12345')
        participant.size = 'Medium'
        participant.address = 'this is my address'
        event2017.addParticipant(participant)
        
        participant = EventParticipant('789456')
        participant.size = 'Large'
        participant.address = 'this is their address'
        event2017.addParticipant(participant)
        
        participant = EventParticipant('354654')
        participant.size = 'XXL'
        participant.address = 'Another address'
        event2017.addParticipant(participant)
    except ValueError as err:
        print("An error occurred: {0}.".format(err))
    
    event2017.status()
    event2017.save()
    event2017 = None
    
    newEvent = JSONtoObject('config/event_2017.json')
    print(newEvent)
    
'''
    eJSON = event2017.toJSON()
    print(eJSON)
    event2017 = None
    
    newEvent = json2obj(eJSON)
    newerEvent = Event(eventName, 0)
    newerEvent.loadObj(newEvent)

    try:
        participant = EventParticipant('id98764')
        participant.size = 'Medium'
        participant.address = 'new address, goes here'
        newerEvent.addParticipant(participant)
        
        participant = EventParticipant('id65468768434')
        participant.size = 'XS'
        participant.address = 'this is, a fake, address'
        newerEvent.addParticipant(participant)
    except ValueError as err:
        print("An error occurred: {0}.".format(err))
        
    print("\n\nNew Obj:\n{0}".format(newerEvent.toJSON()))
    newerEvent.save()
'''
    
if __name__ == '__main__':
    #main()
    #xml_event_status()
    #json_event_status()
    json_event_test()
    print("OK.")
