#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License,
    or (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
    See the GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program; if not, see <http://www.gnu.org/licenses/>.
    
    @author: spoob
    @author: RaNaN
    @author: mkaay
    @version: v0.3.2
"""

import base64
import time
from os import sep, rename, stat
from os.path import exists
import urllib
from cStringIO import StringIO
import pycurl
from tempfile import NamedTemporaryFile
from os import remove

class AbortDownload(Exception):
    pass

class Request:
    def __init__(self, cookieFile=None):

        self.dl_time = 0
        self.dl_finished = 0
        self.dl_size = 0
        self.dl_arrived = 0
        self.dl = False

        self.abort = False

        self.lastEffectiveURL = None
        self.lastURL = None
        self.auth = False
        
        self.timeout = 5
        
        bufferBase = 1024
        bufferMulti = 4
        self.bufferSize = bufferBase*bufferMulti
        self.canContinue = False
        self.offset = 0
        
        self.dl_speed = 0.0
        self.averageSpeed = 0.0
        self.averageSpeeds = []
        self.averageSpeedTime = 0.0
        self.averageSpeedCount = 0.0
        
        self.speedLimitActive = False
        self.maxSpeed = 0
        self.isSlow = False
        
        if not cookieFile:
            th = NamedTemporaryFile(mode="w", prefix="pyload_cookies", delete=False)
            cookieFile = th.name
            th.close()
        self.cookieFile = cookieFile

        self.init_curl()

    def set_timeout(self, timeout):
        self.timeout = int(timeout)

    def init_curl(self):
        self.rep = StringIO()
        self.header = ""

        self.pycurl = pycurl.Curl()
        self.pycurl.setopt(pycurl.FOLLOWLOCATION, 1)
        self.pycurl.setopt(pycurl.MAXREDIRS, 5)
        self.pycurl.setopt(pycurl.TIMEOUT, (self.timeout*3600))
        self.pycurl.setopt(pycurl.CONNECTTIMEOUT, 30)
        self.pycurl.setopt(pycurl.NOSIGNAL, 1)
        self.pycurl.setopt(pycurl.NOPROGRESS, 0)
        self.pycurl.setopt(pycurl.PROGRESSFUNCTION, self.progress)
        self.pycurl.setopt(pycurl.AUTOREFERER, 1)
        self.pycurl.setopt(pycurl.HEADERFUNCTION, self.write_header)
        self.pycurl.setopt(pycurl.BUFFERSIZE, self.bufferSize)


        self.pycurl.setopt(pycurl.USERAGENT, "Mozilla/5.0 (Windows; U; Windows NT 5.1; en; rv:1.9.0.8) Gecko/2009032609 Firefox/3.0.10")
        self.pycurl.setopt(pycurl.ENCODING, "gzip, deflate")
        self.pycurl.setopt(pycurl.HTTPHEADER, ["Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                           "Accept-Charset: ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                           "Connection: keep-alive",
                           "Keep-Alive: 300"])

    def load(self, url, get={}, post={}, ref=True, cookies=True, just_header=False):

        url = str(url)

        if post:
            post = urllib.urlencode(post)
        else:
            post = None

        if get:
            get = urllib.urlencode(get)
            url = "%s?%s" % (url, get)
        else:
            get = ""

        self.pycurl.setopt(pycurl.URL, url)
        self.pycurl.setopt(pycurl.WRITEFUNCTION, self.rep.write)
        
        if cookies:
            self.curl_enable_cookies()

        if post:
            self.pycurl.setopt(pycurl.POSTFIELDS, post)

        if ref and self.lastURL is not None:
            self.pycurl.setopt(pycurl.REFERER, self.lastURL)

        if just_header:
            self.pycurl.setopt(pycurl.NOPROGRESS, 1)
            self.pycurl.setopt(pycurl.NOBODY, 1)
            self.pycurl.perform()
            self.lastEffectiveURL = self.pycurl.getinfo(pycurl.EFFECTIVE_URL)
            self.pycurl.setopt(pycurl.NOPROGRESS, 0)
            self.pycurl.setopt(pycurl.NOBODY, 0)
            return self.header

        self.pycurl.perform()
        
        self.lastEffectiveURL = self.pycurl.getinfo(pycurl.EFFECTIVE_URL)
        self.lastURL = url
        header = self.get_header()

        return self.get_rep()

    def curl_enable_cookies(self):
        self.pycurl.setopt(pycurl.COOKIEFILE, self.cookieFile)
        self.pycurl.setopt(pycurl.COOKIEJAR, self.cookieFile)

    def add_auth(self, user, pw):
        
        self.auth = True
        self.user = user
        self.pw = pw
        
        upwstr = str("%s:%s" % (user,pw))
        self.pycurl.setopt(pycurl.HTTPHEADER, ['Authorization: Basic ' + base64.encodestring(upwstr)[:-1]])
        self.pycurl.setopt(pycurl.USERPWD, upwstr)
        self.pycurl.setopt(pycurl.HTTPAUTH, pycurl.HTTPAUTH_ANY)

    def add_cookies(self, req):
        cookie_head = ""
        for cookie in self.cookies:
            cookie_head += cookie.name + "=" + cookie.value + "; "
        req.add_header("Cookie", cookie_head)

    def clear_cookies(self):
        self.pycurl.setopt(pycurl.COOKIELIST, "")

    def add_proxy(self, protocol, adress):
        # @TODO: pycurl proxy protocoll selection
        self.pycurl.setopt(pycurl.PROXY, adress.split(":")[0])
        self.pycurl.setopt(pycurl.PROXYPORT, adress.split(":")[1])

    def download(self, url, file_name, get={}, post={}, ref=True, cookies=True):

        url = str(url)

        if post:
            post = urllib.urlencode(post)
        else:
            post = None

        if get:
            get = urllib.urlencode(get)
            url = "%s?%s" % (url, get)
        else:
            get = ""

        file_temp = self.get_free_name(file_name) + ".part"
        if not self.canContinue:
            self.fp = open(file_temp, 'wb')
        else:
            self.fp = open(file_temp, 'ab')
        partSize = self.fp.tell()

        self.init_curl()

        self.pycurl.setopt(pycurl.URL, url)
        
        if self.canContinue:
            self.offset = stat(file_temp).st_size
            self.pycurl.setopt(pycurl.RESUME_FROM, self.offset)
            
        self.dl_arrived = self.offset
        
        if cookies:
            self.curl_enable_cookies()

        if post:
            self.pycurl.setopt(pycurl.POSTFIELDS, post)
        
        if self.auth:
            self.add_auth(self.user, self.pw)

        if ref and self.lastURL is not None:
            self.pycurl.setopt(pycurl.REFERER, self.lastURL)

        self.dl_time = time.time()
        self.dl = True
        
        self.chunkSize = 0
        self.chunkRead = 0
        self.subStartTime = 0
        self.maxChunkSize = 0
        
        def restLimit():
            subTime = time.time() - self.subStartTime
            if subTime <= 1:
                if self.speedLimitActive:
                    return self.maxChunkSize
                else:
                    return -1
            else:
                self.updateCurrentSpeed(float(self.chunkRead/1024) / subTime)
                
                self.subStartTime = time.time()
                self.chunkRead = 0
                if self.maxSpeed > 0:
                    self.maxChunkSize = self.maxSpeed
                else:
                    self.maxChunkSize = 0
                return 0

        def writefunc(buf):
            if self.abort:
                return False
            chunkSize = len(buf)
            while chunkSize > restLimit() > -1:
                time.sleep(0.05)
            self.maxChunkSize -= chunkSize
            self.fp.write(buf)
            self.chunkRead += chunkSize
            self.dl_arrived += chunkSize
            
        self.pycurl.setopt(pycurl.WRITEFUNCTION, writefunc)
        
        try:
            self.pycurl.perform()
        except Exception, e:
            code, msg = e
            if not code == 23:
                raise Exception, e
                
        self.fp.close()
        
        if self.abort:
            raise AbortDownload

        free_name = self.get_free_name(file_name)
        rename(file_temp, free_name)
        
        self.dl = False
        self.dl_finished = time.time()

        return free_name
    
    def updateCurrentSpeed(self, speed):
        self.dl_speed = speed
        if self.averageSpeedTime + 10 < time.time():
            self.averageSpeeds = []
            self.averageSpeeds.append(self.averageSpeed)
            self.averageSpeeds.append(speed)
            self.averageSpeed = (speed + self.averageSpeed)/2
            self.averageSpeedTime = time.time()
            self.averageSpeedCount = 2
        else:
            self.averageSpeeds.append(speed)
            self.averageSpeedCount += 1
            allspeed = 0.0
            for s in self.averageSpeeds:
                allspeed += s
            self.averageSpeed = allspeed / self.averageSpeedCount
    
    def write_header(self, string):
        self.header += string

    def get_rep(self):
        value = self.rep.getvalue()
        self.rep.close()
        self.rep = StringIO()
        return value
    
    def get_header(self):
        h = self.header
        self.header = ""
        return h

    def get_speed(self):
        try:
            return self.dl_speed
        except:
            return 0

    def get_ETA(self):
        try:
            return (self.dl_size - self.dl_arrived) / (self.dl_arrived / (time.time() - self.dl_time))
        except:
            return 0

    def kB_left(self):
        return (self.dl_size - self.dl_arrived) / 1024
    
    def progress(self, dl_t, dl_d, up_t, up_d):
        if self.abort:
            return False
        self.dl_arrived = int(dl_d)
        self.dl_size = int(dl_t)

    def get_free_name(self, file_name):
        file_count = 0
        while exists(file_name):
            file_count += 1
            if "." in file_name:
                file_split = file_name.split(".")
                temp_name = "%s-%i.%s" % (".".join(file_split[:-1]), file_count, file_split[-1])
            else:
                temp_name = "%s-%i" % (file_name, file_count)
            if not exists(temp_name):
                file_name = temp_name
        return file_name
    
    def __del__(self):
        self.clean()
    
    def clean(self):
        try:
            self.pycurl.close()
        except:
            pass
        try:
            remove(self.cookieFile)
        except Exception as e:
            pass

def getURL(url):
    """
        currently used for update check
    """
    req = Request()
    c = req.load(url)
    req.pycurl.close()
    return c

if __name__ == "__main__":
    import doctest
    doctest.testmod()
