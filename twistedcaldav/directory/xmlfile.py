##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# DRI: Cyrus Daboo, cdaboo@apple.com
##


"""
XML based user/group/resource directory service implementation.
"""

__all__ = [
    "XMLFileService",
    "XMLFileRecord",
]

import xml.dom.minidom

from twisted.cred.credentials import UsernamePassword
from twisted.python.filepath import FilePath

from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord
from twistedcaldav.resource import CalDAVResource

ELEMENT_ACCOUNTS    = "accounts"
ELEMENT_USER        = "user"
ELEMENT_GROUP       = "group"
ELEMENT_RESOURCE    = "resource"

ELEMENT_USERID      = "uid"
ELEMENT_PASSWORD    = "pswd"
ELEMENT_NAME        = "name"
ELEMENT_MEMBERS     = "members"
ELEMENT_CUADDR      = "cuaddr"
ELEMENT_CALENDAR    = "calendar"
ELEMENT_QUOTA       = "quota"
ELEMENT_AUTORESPOND = "autorespond"
ELEMENT_CANPROXY    = "canproxy"

ATTRIBUTE_REPEAT    = "repeat"

class XMLFileService(DirectoryService):
    """
    XML based implementation of L{IDirectoryService}.
    """
    def __repr__(self):
        return "<%s %r>" % (self.__class__.__name__, self.xmlFile)

    def __init__(self, xmlFile):
        if type(xmlFile) is str:
            xmlFile = FilePath(xmlFile)

        self.xmlFile = xmlFile
        self.items = {}

    def recordTypes(self):
        recordTypes = ("user", "group", "resource")
        return recordTypes

    def listRecords(self, recordType):
        for entryShortName, xmlprincipal in self._entriesForRecordType(recordType):
            yield entryShortName

    def recordWithShortName(self, recordType, shortName):
        for entryShortName, xmlprincipal in self._entriesForRecordType(recordType):
            if entryShortName == shortName:
                return XMLFileRecord(
                    service       = self,
                    recordType    = recordType,
                    shortName     = entryShortName,
                    xmlPrincipal  = xmlprincipal,
                )

        raise NotImplementedError()

    def recordWithGUID(self, guid):
        raise NotImplementedError()

    def _entriesForRecordType(self, recordType):
        # Read in XML
        fd = open(self.xmlFile.path, "r")
        doc = xml.dom.minidom.parse( fd )
        fd.close()

        # Verify that top-level element is correct
        accounts_node = doc._get_documentElement()
        if accounts_node._get_localName() != ELEMENT_ACCOUNTS:
            self.log("Ignoring file %r because it is not a repository builder file" % (self.xmlFile,))
            return
        self._parseXML(accounts_node)
        
        for entry in self.items.itervalues():
            if entry.recordType == recordType:
                 yield entry.uid, entry
             
        self.items = {}

    def _parseXML(self, node):
        """
        Parse the XML root node from the accounts configuration document.
        @param node: the L{Node} to parse.
        """
        self.items = {}
        for child in node._get_childNodes():
            if child._get_localName() in (ELEMENT_USER, ELEMENT_GROUP, ELEMENT_RESOURCE):
                if child.hasAttribute( ATTRIBUTE_REPEAT ):
                    repeat = int(child.getAttribute( ATTRIBUTE_REPEAT ))
                else:
                    repeat = 1

                recordType = {
                    ELEMENT_USER:    "user",
                    ELEMENT_GROUP:   "group",
                    ELEMENT_RESOURCE:"resource",}[child._get_localName()]
                
                principal = XMLPrincipal(recordType)
                principal.parseXML( child )
                if repeat > 1:
                    for ctr in range(repeat):
                        newprincipal = principal.repeat(ctr + 1)
                        self.items[newprincipal.uid] = newprincipal
                        if recordType == "group":
                            self._updateMembership(newprincipal)
                else:
                    self.items[principal.uid] = principal
                    if recordType == "group":
                        self._updateMembership(principal)

    def _updateMembership(self, group):
        # Update group membership
        for member in group.members:
            if self.items.has_key(member):
                self.items[member].groups.append(group.uid)
        
class XMLPrincipal (object):
    """
    Contains provision information for one user.
    """
    def __init__(self, recordType):
        """
        @param recordType:    record type for directory entry.
        """
        
        self.recordType = recordType
        self.uid = None
        self.pswd = None
        self.name = None
        self.members = []
        self.groups = []
        self.cuaddrs = []
        self.calendars = []
        self.quota = None
        self.autorespond = None

    def repeat(self, ctr):
        """
        Create another object like this but with all text items having % substitution
        done on them with the numeric value provided.
        @param ctr: an integer to substitute into text.
        """
        
        if self.uid.find("%") != -1:
            uid = self.uid % ctr
        else:
            uid = self.uid
        if self.pswd.find("%") != -1:
            pswd = self.pswd % ctr
        else:
            pswd = self.pswd
        if self.name.find("%") != -1:
            name = self.name % ctr
        else:
            name = self.name
        cuaddrs = []
        for cuaddr in self.cuaddrs:
            if cuaddr.find("%") != -1:
                cuaddrs.append(cuaddr % ctr)
            else:
                cuaddrs.append(cuaddr)
        
        result = XMLPrincipal(self.recordType)
        result.uid = uid
        result.pswd = pswd
        result.name = name
        result.members = self.members
        result.cuaddrs = cuaddrs
        result.calendars = self.calendars
        result.quota = self.quota
        result.autorespond = self.autorespond
        return result

    def parseXML( self, node ):

        for child in node._get_childNodes():
            if child._get_localName() == ELEMENT_USERID:
                if child.firstChild is not None:
                   self.uid = child.firstChild.data.encode("utf-8")
            elif child._get_localName() == ELEMENT_PASSWORD:
                if child.firstChild is not None:
                    self.pswd = child.firstChild.data.encode("utf-8")
            elif child._get_localName() == ELEMENT_NAME:
                if child.firstChild is not None:
                   self.name = child.firstChild.data.encode("utf-8")
            elif child._get_localName() == ELEMENT_MEMBERS:
                self._parseMembers(child)
            elif child._get_localName() == ELEMENT_CUADDR:
                if child.firstChild is not None:
                   self.cuaddrs.append(child.firstChild.data.encode("utf-8"))
            elif child._get_localName() == ELEMENT_CALENDAR:
                if child.firstChild is not None:
                   self.calendars.append(child.firstChild.data.encode("utf-8"))
            elif child._get_localName() == ELEMENT_QUOTA:
                if child.firstChild is not None:
                   self.quota = int(child.firstChild.data.encode("utf-8"))
            elif child._get_localName() == ELEMENT_AUTORESPOND:
                self.autorespond = True
            elif child._get_localName() == ELEMENT_CANPROXY:
                CalDAVResource.proxyUsers.add(self.uid)

    def _parseMembers( self, node ):

        for child in node._get_childNodes():
            if child._get_localName() == ELEMENT_USERID:
                if child.firstChild is not None:
                   self.members.append(child.firstChild.data.encode("utf-8"))

class XMLFileRecord(DirectoryRecord):
    """
    XML based implementation implementation of L{IDirectoryRecord}.
    """
    def __init__(self, service, recordType, shortName, xmlPrincipal):

        self.service        = service
        self.recordType     = recordType
        self.guid           = None
        self.shortName      = shortName
        self.fullName       = xmlPrincipal.name
        self.clearPassword  = xmlPrincipal.pswd
        self._members       = xmlPrincipal.members
        self._groups        = xmlPrincipal.groups

    def members(self):
        for shortName in self._members:
            yield self.service.recordWithShortName("user", shortName)

    def groups(self):
        for shortName in self._groups:
            yield self.service.recordWithShortName("group", shortName)

    def verifyCredentials(self, credentials):
        if isinstance(credentials, UsernamePassword):
            return credentials.password == self.clearPassword

        return super(XMLFileRecord, self).verifyCredentials(credentials)
