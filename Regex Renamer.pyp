# -*- coding: UTF-8  -*-
#
#  Regex Renamer.pyp
#  CINEMA 4D Python Plugins
#
#  Created by Andre Berg on 2011-04-02.
#  Copyright 2011 Berg Media. All rights reserved.
#
#  Version 0.2
#  Updated: 2011-04-04
#
#  Summary: Search for and rename objects
#  using Python's power re module
#
#

import os
import re
import ConfigParser
import c4d
from c4d import plugins, bitmaps, gui, documents
from c4d.utils import *

DEBUG = False

if DEBUG:
    import pprint
    pp = pprint.PrettyPrinter(width=200)
    PP = pp.pprint
    PF = pp.pformat


# -------------------------------------------
#                GLOBALS
# -------------------------------------------

PLUGIN_NAME    = "Regex Renamer"
PLUGIN_VERSION = 1.0
PLUGIN_HELP    = "Find & Replace object names using Python's powerful re module"
PLUGIN_ABOUT   = """(C) 2011 Andre Berg (Berg Media)
All rights reserved.

Regex Renamer is a command plugin, that
allows for utilizing Python's powerful "re"
module to perform regular expression based
searching and replacing within object names.

Use at your own risk!

It is recommended to try out the plugin
on a spare copy of your data first.
"""

IDS_HINT_NONASCII = """When searching, non-ASCII characters like 
for example German umlauts, need to be escaped 
with a single backslash. It seems that for 
Python CINEMA 4D's object manager stores names 
containing higher order Unicode characters 
with a preceeding backslash.
"""

IDS_TIPS1 = """I you leave the "Replace with:" field empty, 
matching objects will be selected but no 
replacing will be performed.
"""

IDS_SETTINGS_PARSE_ERROR_SEARCHREGEX_UNKNOWN = "Parsing 'Search for' failed. The error message was: %s"
IDS_SETTINGS_PARSE_ERROR_REPLACEREGEX_UNKNOWN = "Parsing 'Replace with' failed. The error message was: %s"
IDS_SETTINGS_COMPILE_ERROR_SEARCHREGEX = "Compiling regex in 'Search for' failed. The error message was: %s"
IDS_SETTINGS_PARSE_ERROR_WRONG_SYNTAX = """Please use pure regex syntax only. Term will be wrapped in ur'<term>'."""
IDS_SETTINGS_PARSE_ERROR_BLACKLISTED = "Error: please refrain from using the following words: 'import os', 'removedirs', 'remove', 'rmdir'"

BLACKLIST = ['import os', 'removedirs', 'remove', 'rmdir']

# Defaults
DEFAULT_SEARCH_REGEX = "(.*?)\.(\d)"
DEFAULT_REPLACE_REGEX = "\\2-\\1"
DEFAULT_IGNORECASE = False
DEFAULT_MULTILINE = False
DEFAULT_DOTALL = False
DEFAULT_VERBOSE = False
DEFAULT_SELECTIONONLY = False

# -------------------------------------------
#               PLUGING IDS
# -------------------------------------------

# unique ID
ID_REGEXRENAMER = 1026925


# Element IDs
IDD_DIALOG_SETTINGS     = 10001
IDC_GROUP_WRAPPER       = 10002
IDC_GROUP_SETTINGS      = 10003
IDC_STATIC_SEARCH       = 10004
IDC_EDIT_SEARCH         = 10005
IDC_STATIC_REPLACE      = 10006
IDC_EDIT_REPLACE        = 10007
IDC_CHECK_IGNORECASE    = 10008
IDC_CHECK_MULTILINE     = 10009
IDC_CHECK_DOTALL        = 10010
IDC_CHECK_VERBOSE       = 10011
IDC_GROUP_SETTINGS2     = 10012
IDC_CHECK_SELECTIONONLY = 10013
IDC_GROUP_BUTTONS       = 10014
IDC_BUTTON_CANCEL       = 10015
IDC_BUTTON_DOIT         = 10016
IDC_DUMMY               = 10017
IDC_MENU_ABOUT          = 30001
IDC_MENU_TUTORIAL       = 30002
IDC_MENU_HINT_NONASCII  = 30003
IDC_MENU_TIPS           = 30004

# String IDs
IDS_DIALOG_TITLE         = PLUGIN_NAME
IDS_MENU_INFO            = "Info"
IDS_MENU_ABOUT           = "About..."
IDS_MENU_TUTORIAL        = "Online tutorial..."
IDS_MENU_HINT_NONASCII   = "Unicode chars..."
IDS_MENU_TIPS            = "Tips..."


class Helpers(object):
    """Contains various helper methods."""
    def __init__(self, arg):
        super(Helpers, self).__init__()
    
    @staticmethod
    def readConfig(filepath=None):
        """
        Read settings from a configuration file.
        
        Returns None if config file at filepath doesn't exist.
        Returns the config object on success.
        """
        result = None
        if filepath is None:
            filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "res", "config.ini")
        if os.path.exists(filepath):
            config = ConfigParser.ConfigParser()
            config.read(filepath)
            result = config
        return result
    
    @staticmethod
    def saveConfig(config, filepath=None):
        """
        Save settings to a configuration file.
        
        If filepath is None, it will be assumed to point to res/config.ini.
        Returns True if successful, False otherwise.
        """
        result = False
        if filepath is None:
            filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "res", "config.ini")
        try:
            with open(filepath, 'wb') as configfile:
                config.write(configfile)
            result = True
        except Exception, e:
            print "Error writing config file to '%s': %r" % (filepath, e)
        return result
    
    @staticmethod
    def initConfig(defaults, filepath=None):
        """
        Initialize configuration file by writing the defaults.
        
        Returns True if config file was created,
        False if config file already exists or otherwise.
        """
        result = False
        if filepath is None:
            filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "res", "config.ini")
        if not os.path.exists(filepath):
            config = ConfigParser.ConfigParser(defaults)
            result = Helpers.saveConfig(config, filepath)
        return result
    
    @staticmethod
    def select(op):
        if not op.GetBit(c4d.BIT_ACTIVE):
            op.ToggleBit(c4d.BIT_ACTIVE)
        return op.GetBit(c4d.BIT_ACTIVE)
    
    @staticmethod
    def selectObjects(objs):
        for op in objs:
            Helpers.select(op)
    
    @staticmethod
    def deselectAll(inObjMngr=False):
        """
        Not the same as BaseSelect.DeselectAll().
        
        inObjMngr  bool  if True, run the deselect command from Object Manager,
                         else the general one for editor viewport
        """
        if inObjMngr is True:
            c4d.CallCommand(100004767) # deselect all (Object Manager)
        else:
            c4d.CallCommand(12113) # deselect all
    
    @staticmethod
    def getNextObject(op, stopobj=None):
        if op is None: return None
        if op.GetDown(): return op.GetDown()
        if stopobj is None:
            while not op.GetNext() and op.GetUp():
                    op = op.GetUp()
        else:
            while (not op.GetNext() and 
                       op.GetUp() and 
                       op.GetUp() != stopobj):
                op = op.GetUp()
        return op.GetNext()
    

# ------------------------------------------------------
#                   User Interface
# ------------------------------------------------------
class RegexRenamerDialog(gui.GeDialog):
    
    def CreateLayout(self):
        self.SetTitle(IDS_DIALOG_TITLE)
        
        plugins.GeResource().Init(os.path.dirname(os.path.abspath(__file__)))
        self.LoadDialogResource(IDD_DIALOG_SETTINGS, flags=c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT)
        
        # Menu
        self.MenuFlushAll()
        self.MenuSubBegin(IDS_MENU_INFO)
        self.MenuAddString(IDC_MENU_ABOUT, IDS_MENU_ABOUT)
        self.MenuAddString(IDC_MENU_TUTORIAL, IDS_MENU_TUTORIAL)
        self.MenuAddString(IDC_MENU_HINT_NONASCII, IDS_MENU_HINT_NONASCII)
        self.MenuAddString(IDC_MENU_TIPS, IDS_MENU_TIPS)
        self.MenuSubEnd()
        
        self.MenuFinished()
        
        return True
    
    def InitValues(self):
        config = Helpers.readConfig()
        if config is not None:
            searchregex = config.get("Settings", "search")
            replaceterm = config.get("Settings", "replace")
            ignorecase = config.getboolean("Settings", "ignorecase")
            multiline = config.getboolean("Settings", "multiline")
            verbose = config.getboolean("Settings", "verbose")
            selectiononly = config.getboolean("Settings", "selectiononly")
            dotall = config.getboolean("Settings", "dotall")
            if DEBUG:
                print "stored search regex = %s" % searchregex
                print "stored replace term = %s" % replaceterm
                print "stored ignorecase = %s" % ignorecase
                print "stored multiline = %s" % multiline
                print "stored verbose = %s" % verbose
                print "stored dot all = %s" % dotall
                print "stored selection only = %s" % selectiononly
        else:
            searchregex = DEFAULT_SEARCH_REGEX
            replaceterm = DEFAULT_REPLACE_REGEX
            ignorecase = DEFAULT_IGNORECASE
            multiline = DEFAULT_MULTILINE
            verbose = DEFAULT_VERBOSE
            dotall = DEFAULT_DOTALL
            selectiononly = DEFAULT_SELECTIONONLY
            # if the config file isn't there, create it
            config = ConfigParser.ConfigParser()
            config.add_section("Settings")
            config.set("Settings", "search", searchregex)
            config.set("Settings", "replace", replaceterm)
            config.set("Settings", "ignorecase", ignorecase)
            config.set("Settings", "multiline", multiline)
            config.set("Settings", "verbose", verbose)
            config.set("Settings", "dotall", dotall)
            config.set("Settings", "selectiononly", selectiononly)
            Helpers.saveConfig(config)
        self.SetString(IDC_EDIT_SEARCH, searchregex)
        self.SetString(IDC_EDIT_REPLACE, replaceterm)
        self.SetBool(IDC_CHECK_IGNORECASE, ignorecase)
        self.SetBool(IDC_CHECK_MULTILINE, multiline)
        self.SetBool(IDC_CHECK_VERBOSE, verbose)
        self.SetBool(IDC_CHECK_DOTALL, dotall)
        self.SetBool(IDC_CHECK_SELECTIONONLY, selectiononly)
        if len(replaceterm) > 0:
            self.SetString(IDC_BUTTON_DOIT, "Replace")
        else:
            self.SetString(IDC_BUTTON_DOIT, "Select")
        return True
    
    def Command(self, id, msg):
        
        cursearchregex = self.GetString(IDC_EDIT_SEARCH)
        curreplaceterm = self.GetString(IDC_EDIT_REPLACE)
        multiline = self.GetBool(IDC_CHECK_MULTILINE)
        ignorecase = self.GetBool(IDC_CHECK_IGNORECASE)
        dotall = self.GetBool(IDC_CHECK_DOTALL)
        verbose = self.GetBool(IDC_CHECK_VERBOSE)
        selectiononly = self.GetBool(IDC_CHECK_SELECTIONONLY)
        
        if id == IDC_BUTTON_DOIT:
            
            # sanitize input
            for s in BLACKLIST:
                if s in cursearchregex or s in curreplaceterm:
                    c4d.gui.MessageDialog(IDS_SETTINGS_PARSE_ERROR_BLACKLISTED)
                    return False
            try:
                evalsearchregex = eval("ur\"\"\"%s\"\"\"" % cursearchregex)
            except Exception, e:
                c4d.gui.MessageDialog(IDS_SETTINGS_PARSE_ERROR_SEARCHREGEX_UNKNOWN % e)
                return False
            try:
                evalreplaceterm = eval("ur\"\"\"%s\"\"\"" % curreplaceterm)
            except Exception, e:
                c4d.gui.MessageDialog(IDS_SETTINGS_PARSE_ERROR_REPLACEREGEX_UNKNOWN % e)
                return False
            
            scriptvars = {
                'search': evalsearchregex,
                'replace': evalreplaceterm,
                'multiline': multiline,
                'ignorecase': ignorecase,
                'dotall': dotall,
                'verbose': verbose,
                'selectiononly': selectiononly
            }
            script = RegexRenamerScript(scriptvars)
            if DEBUG:
                print "do it: %r" % msg
                print "script = %r" % script
                print "scriptvars = %r" % scriptvars
                
            return script.run()
        
        elif id == IDC_BUTTON_CANCEL:
            
            searchregex = self.GetString(IDC_EDIT_SEARCH)
            replaceterm = self.GetString(IDC_EDIT_REPLACE)
            multiline = self.GetBool(IDC_CHECK_MULTILINE)
            ignorecase = self.GetBool(IDC_CHECK_IGNORECASE)
            dotall = self.GetBool(IDC_CHECK_DOTALL)
            verbose = self.GetBool(IDC_CHECK_VERBOSE)
            selectiononly = self.GetBool(IDC_CHECK_SELECTIONONLY)
            
            if DEBUG:
                print "cancel: %r" % msg
                print "search: %r" % searchregex
                print "replace: %r" % replaceterm
                print "ignorecase: %s" % ignorecase
                print "multiline: %s" % multiline
                print "verbose: %s" % verbose
                print "dot all: %s" % dotall
                print "selection only: %s" % selectiononly
            config = Helpers.readConfig()
            if config is not None:
                config.set("Settings", "search", searchregex)
                config.set("Settings", "replace", replaceterm)
                config.set("Settings", "ignorecase", ignorecase)
                config.set("Settings", "multiline", multiline)
                config.set("Settings", "verbose", verbose)
                config.set("Settings", "dotall", dotall)
                config.set("Settings", "selectiononly", selectiononly)
                Helpers.saveConfig(config)
            self.Close()
        
        # elif id == IDC_EDIT_SEARCH:
        #     
        #     searchregex = self.GetString(IDC_EDIT_SEARCH)
        #     config = Helpers.readConfig()
        #     if config is not None:
        #         config.set("Settings", "search", searchregex)
        #         Helpers.saveConfig(config)
        #     if DEBUG:
        #         print "edit search regex: %r" % msg
        #         print "searchregex = %s" % searchregex
        # 
        elif id == IDC_EDIT_REPLACE:
            
            replaceterm = self.GetString(IDC_EDIT_REPLACE)
            # config = Helpers.readConfig()
            # if config is not None:
            #     config.set("Settings", "replace", replaceterm)
            #     Helpers.saveConfig(config)
            # if DEBUG:
            #     print "edit replace term: %r" % msg
            #     print "replaceterm = %s" % replaceterm
            if len(replaceterm) > 0:
                self.SetString(IDC_BUTTON_DOIT, "Replace")
            else:
                self.SetString(IDC_BUTTON_DOIT, "Select")
                    
        elif id == IDC_MENU_ABOUT:
            
            c4d.gui.MessageDialog(PLUGIN_ABOUT)
        
        elif id == IDC_MENU_TUTORIAL:
            
            thispath = os.path.dirname(os.path.abspath(__file__))
            tutorialfile = os.path.join(thispath, "res", "tutorial.html")
            c4d.storage.GeExecuteFile(tutorialfile)
        
        elif id == IDC_MENU_HINT_NONASCII:
            
            c4d.gui.MessageDialog(IDS_HINT_NONASCII)
        
        elif id == IDC_MENU_TIPS:
            
            c4d.gui.MessageDialog(IDS_TIPS1)
            
        else:
            if DEBUG:
                print "id = %s" % id
        
        return True
    


# ------------------------------------------------------
#                   Command Script
# ------------------------------------------------------
class RegexRenamerScript(object):
    """Run when the user clicks the OK button."""
    def __init__(self, scriptvars=None):
        super(RegexRenamerScript, self).__init__()
        self.data = scriptvars
    
    def run(self):
        doc = documents.GetActiveDocument()
        if doc is None: return False
        
        doc.StartUndo()
                        
        searchregex = self.data['search']
        replaceterm = self.data['replace']
        ignorecase = self.data['ignorecase']
        multiline = self.data['multiline']
        verbose = self.data['verbose']
        dotall = self.data['dotall']
        selectiononly = self.data['selectiononly']
        
        flags = re.UNICODE
        if ignorecase is True:
            flags = flags | re.IGNORECASE
        if multiline is True:
            flags = flags | re.MULTILINE
        if verbose is True:
            flags = flags | re.VERBOSE
        if dotall is True:
            flags = flags | re.DOTALL
        
        try:
            pat = re.compile(searchregex, flags)
        except Exception, e:
            c4d.gui.MessageDialog(IDS_SETTINGS_COMPILE_ERROR_SEARCHREGEX % e)
            return False
                
        # very important!
        c4d.StopAllThreads()
                
        c4d.StatusSetSpin()
        timestart = c4d.GeGetMilliSeconds()
        
        if selectiononly:
            sel = doc.GetSelection()
            if sel is None or len(sel) == 0: return False
            Helpers.deselectAll(True)
            for op in sel:
                curname = op.GetName()
                if DEBUG: print "processing %r (%r)" % (curname, op)
                if re.search(pat, curname):
                    doc.AddUndo(c4d.UNDOTYPE_CHANGE, op)
                    Helpers.select(op)
                    if len(replaceterm) > 0:
                        newname = re.sub(pat, replaceterm, curname)
                        op.SetName(newname)
                        op.Message(c4d.MSG_UPDATE)
                        c4d.EventAdd()
        else:
            Helpers.deselectAll(True)
            op = doc.GetFirstObject()
            while op:
                curname = op.GetName()
                if DEBUG: print "processing %r (%r)" % (curname, op)
                if re.search(pat, curname):
                    doc.AddUndo(c4d.UNDOTYPE_CHANGE, op)
                    Helpers.select(op)
                    if len(replaceterm) > 0:
                        newname = re.sub(pat, replaceterm, curname)
                        op.SetName(newname)
                        op.Message(c4d.MSG_UPDATE)
                        c4d.EventAdd()
                op = Helpers.getNextObject(op)
        
        c4d.StatusClear()
        
        # tell C4D to update internal state
        c4d.EventAdd()
        doc.EndUndo()
        
        timeend = int(c4d.GeGetMilliSeconds() - timestart)
        timemsg = "RegexRenamer: finished in " + str(timeend) + " milliseconds"
        print timemsg
        
        return True
    

# ----------------------------------------------------
#                      Main
# ----------------------------------------------------
class RegexRenamerMain(plugins.CommandData):
    dialog = None
    def Execute(self, doc):
        # create the dialog
        if self.dialog is None:
            self.dialog = RegexRenamerDialog()
        return self.dialog.Open(c4d.DLG_TYPE_ASYNC, pluginid=ID_REGEXRENAMER, defaultw=355, defaulth=200)
    
    def RestoreLayout(self, secref):
        # manage nonmodal dialog
        if self.dialog is None:
            self.dialog = RegexRenamerDialog()
        return self.dialog.Restore(pluginid=ID_REGEXRENAMER, secret=secref)
    


if __name__ == "__main__":
    thispath = os.path.dirname(os.path.abspath(__file__))
    icon = bitmaps.BaseBitmap()
    icon.InitWith(os.path.join(thispath, "res", "icon.png"))
    plugins.RegisterCommandPlugin(
        ID_REGEXRENAMER,
        PLUGIN_NAME,
        0,
        icon,
        PLUGIN_HELP,
        RegexRenamerMain()
    )
    print "%s v%.1f loaded. (C) 2011 Andre Berg" % (PLUGIN_NAME, PLUGIN_VERSION)


# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
