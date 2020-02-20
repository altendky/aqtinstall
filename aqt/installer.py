#!/usr/bin/env python3
#
# Copyright (C) 2018 Linus Jahn <lnj@kaidan.im>
# Copyright (C) 2019,2020 Hiroshi Miura <miurahr@linux.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import functools
import multiprocessing.dummy
import os
import subprocess
from logging import getLogger
from operator import and_

import requests

import py7zr
from aqt.helper import altlink


class BadPackageFile(Exception):
    pass


class QtInstaller:
    """
    Installer class to download packages and extract it.
    """

    def __init__(self, qt_archives, logging=None, command=None, target_dir=None):
        self.qt_archives = qt_archives
        if logging:
            self.logger = logging
        else:
            self.logger = getLogger('aqt')
        self.command = command
        if target_dir is None:
            self.base_dir = os.getcwd()
        else:
            self.base_dir = target_dir

    def retrieve_archive(self, package):
        archive = package.archive
        url = package.url
        self.logger.info("Downloading {}...".format(url))
        try:
            r = requests.get(url, allow_redirects=False, stream=True)
            if r.status_code == 302:
                newurl = altlink(r.url)
                # newurl = r.headers['Location']
                self.logger.info('Redirected to new URL: {}'.format(newurl))
                r = requests.get(newurl, stream=True)
        except requests.exceptions.ConnectionError as e:
            self.logger.warning("Caught download error: %s" % e.args)
            return False
        else:
            try:
                with open(archive, 'wb') as fd:
                    for chunk in r.iter_content(chunk_size=8196):
                        fd.write(chunk)
            except Exception as e:
                self.logger.warning("Caught download error: %s" % e.args)
                return False
        self.logger.info("Download {} finished.".format(url))
        return True

    def extract_archive(self, package):
        try:
            archive = package.archive
            self.logger.info("Extracting {}...".format(archive))
            szip = py7zr.SevenZipFile(archive)
            szip.extractall(path=self.base_dir)
            szip.close()
            os.unlink(archive)
        except Exception:
            return False
        else:
            self.logger.info("Extracted {}".format(archive))
            return True

    def extract_archive_ext(self, package):
        try:
            archive = package.archive
            self.logger.info("Extracting {}...".format(archive))
            if self.base_dir is not None:
                subprocess.run([self.command, 'x', '-aoa', '-bd', '-y', '-o{}'.format(self.base_dir), archive])
            else:
                subprocess.run([self.command, 'x', '-aoa', '-bd', '-y', archive])
            os.unlink(archive)
        except Exception:
            return False
        else:
            return True

    def install(self):
        qt_version, target, arch = self.qt_archives.get_target_config()
        if self.command is None:
            extractor = self.extract_archive
        else:
            extractor = self.extract_archive_ext
        archives = self.qt_archives.get_archives()
        p = multiprocessing.dummy.Pool(3)
        ret_arr = p.map(self.retrieve_archive, archives)
        ret = functools.reduce(and_, ret_arr)
        if ret:
            self.logger.info("Downloads are Completed.")
        else:
            self.logger.error("Failed to download.")
        p = multiprocessing.dummy.Pool()
        ret_arr = p.map(extractor, archives)
        ret = functools.reduce(and_, ret_arr)
        if ret:
            self.logger.info("Extractions are Completed.")
        else:
            self.logger.error("Failed to extract archvies.")

        # finalize
        if qt_version != "Tools":  # tools installation
            if arch.startswith('win64_mingw'):
                arch_dir = arch[6:] + '_64'
            elif arch.startswith('win32_mingw'):
                arch_dir = arch[6:] + '_32'
            elif arch.startswith('win'):
                arch_dir = arch[6:]
            else:
                arch_dir = arch
            self.make_conf_files(qt_version, arch_dir)
        self.logger.info("Finished installation")

    def make_conf_files(self, qt_version, arch_dir):
        """Make Qt configuration files, qt.conf and qtconfig.pri"""
        try:
            # prepare qt.conf
            with open(os.path.join(self.base_dir, qt_version, arch_dir, 'bin', 'qt.conf'), 'w') as f:
                f.write("[Paths]\n")
                f.write("Prefix=..\n")
            # update qtconfig.pri only as OpenSource
            with open(os.path.join(self.base_dir, qt_version, arch_dir, 'mkspecs', 'qconfig.pri'), 'r+') as f:
                lines = f.readlines()
                f.seek(0)
                f.truncate()
                for line in lines:
                    if line.startswith('QT_EDITION ='):
                        line = 'QT_EDITION = OpenSource\n'
                    if line.startswith('QT_LICHECK ='):
                        line = 'QT_LICHECK =\n'
                    f.write(line)
        except IOError as e:
            self.logger.error("Configuration file generation error: %s\n", e.args, exc_info=True)
            raise e
