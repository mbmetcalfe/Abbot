#!/usr/bin/python

from xml.dom.minidom import parse
import xml.dom.minidom
from xml.dom.minidom import getDOMImplementation

# Code extrapolated from: https://www.tutorialspoint.com/python/python_xml_processing.htm
# and https://stackoverflow.com/questions/13588072/python-minidom-xml-how-to-set-node-text-with-minidom-api?rq=1

# look here: https://wiki.python.org/moin/MiniDom

# DOM documentation: https://docs.python.org/3/library/xml.dom.html

def replaceText(node, newText):
    if node.firstChild.nodeType != node.TEXT_NODE:
        raise Exception("node does not contain text")

    node.firstChild.replaceWholeText(newText)

def old_main():
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
     print("Name: {0}; Discord Id: {1}.".format(participant.getAttribute("name"), participant.getAttribute("discord_id")))
     giftee = participant.getElementsByTagName('giftee')
     if len(giftee) == 0: # no giftee tag yet, so add one
##         newGiftee = doc.createElement("giftee")
##         newGiftee.setAttribute("name", "BigData")
        newGiftee = doc.createTextNode("giftee")
        participant.appendChild(newGiftee)
     else:
         print("\tGiftee: {0}.".format(giftee))
   print(" ")
##   expertise = doc.getElementsByTagName("expertise")
##   print "%d expertise:" % expertise.length
##   for skill in expertise:
##     print skill.getAttribute("name")
   fileHandle = open("test.xml","w")
   doc.writexml(fileHandle)
   fileHandle.close()
    
if __name__ == '__main__':
    main()
