import re
import os
import urllib3
import ssl

import requests
import wordsegment

from bs4 import BeautifulSoup, ParserRejectedMarkup
from requests.exceptions import MissingSchema, InvalidSchema

FOLLOW_LINKS_CONTAINING = 'download'  # use empty string to follow all
MAXIMUM_LINKS_BETWEEN_LINKS_CONTAINING_TARGET_TEXT = 3
DO_NOT_GO_TO_PLACES_ENDING_IN = ('.txt', '.pdf', )
DO_NOT_GO_TO_PLACES_STARTING_WITH = ('ftp:', 'tel:', )
TARGET_EXTENSIONS = ('.csv', '.xls', '.ashx', '.zip' )
MAX_DEPTH = 20
MAXIMUM_FILE_SIZE = 2e8

FEDERAL_TOP_PAGE = r"https://results.aec.gov.au/"
TOP_PAGES = (FEDERAL_TOP_PAGE, )

CONTENT_TYPE_KEY = 'content-type'
HTML_HEADER_CONTENT_LENGTH_KEY = 'content-length'
CONT_DISP = 'content-disposition'
F_PAT = re.compile(r'filename=(.+)')
FOLDERS_PATTERN = re.compile(r'([0-9]+)[^a-z0-9]*(.*)')


class Inventory(list):
    """
    List of items. __iter__() method returns elements in alphabetical
    order
    """

    def __init__(self):
        list.__init__(self)
        self._sorted = False

    def __iter__(self):
        if not self._sorted:
            self.sort()
            self._sorted = True
        return list.__iter__(self)

    def __call__(self, new_item):
        if new_item in self:
            return False
        self.append(new_item)
        self._sorted = False
        return True

    def follow(self, url, folders, verb=True, lev=0, ext=TARGET_EXTENSIONS,
               ftext=FOLLOW_LINKS_CONTAINING, max_depth=MAX_DEPTH):
        if url and self(url):
            if lev < max_depth:
                try:
                    url_split_on_slashes = url.split("/")
                    stem = "/".join(url_split_on_slashes[:-1])
                    [self._next_node(
                        ftext, lev, node, stem, ext, verb, folders) for node in
                        BeautifulSoup(requests.get(url).text,
                                      'html.parser').find_all('a') if node]
                    if verb:
                        print(' '.join([". " * lev, url_split_on_slashes[-1]]))
                except (InvalidSchema, ParserRejectedMarkup) as schemaException:
                    if verb:
                        print(f"Didn't download {url}. {str(schemaException)}")
                except (MissingSchema, ssl.SSLCertVerificationError,
                        requests.exceptions.SSLError,
                        urllib3.exceptions.SSLError,
                        urllib3.exceptions.MaxRetryError):
                    pass

    def get_year(self, node):
        match = FOLDERS_PATTERN.match(node.string.lower())
        if match:
            self.follow(node.get('href'), (match.group(1), "".join([
                char for char in match.group(2) if char.isalpha()])))

    def fetch(self, url, folders, check_type=False,
              target_type="application/octet-stream"):
        if self(url):
            header = requests.head(url, allow_redirects=True).headers
            if check_type:
                content_type = str(header.get(CONTENT_TYPE_KEY)).lower()
                if content_type == target_type:
                    self._download_target(header, url, folders)
                else:
                    print(f"Didn't download {url}. Wrong type: {content_type}")
            else:
                self._download_target(header, url, folders)

    def _download_target(self, header, url, folders):
        content_length = float(header.get(HTML_HEADER_CONTENT_LENGTH_KEY, None))
        if content_length and content_length <= MAXIMUM_FILE_SIZE:
            self._download_file(url, folders)
        else:
            print(f"Didn't download {url}. Size exceeds {MAXIMUM_FILE_SIZE}")

    def _download_file(self, url, fold):
        get_request = requests.get(url, allow_redirects=True)
        fname = Inventory._guess_filename(get_request, url)
        if fname:
            if self(fname):
                path = os.path.join(*fold, *wordsegment.segment(fname.lower()))
                os.makedirs(path, exist_ok=True)
                with open(os.path.join(path, fname), "wb") as target_file:
                    target_file.write(get_request.content)
        else:
            print(f"Didn't download {url}. Can't guess the fname.")

    def _next_node(self, ftext, lev, node, stem, ext, verb, fld,
                   mlink=MAXIMUM_LINKS_BETWEEN_LINKS_CONTAINING_TARGET_TEXT):
        node_get = node.get('href')
        if node_get:
            next_url = f"{stem}/{node_get}"
            if any([node_get.endswith(target) for target in ext]):
                inv.fetch(next_url, fld)
            elif node.string:
                if (not any([node_get.endswith(skipped) for
                             skipped in DO_NOT_GO_TO_PLACES_ENDING_IN])) and (
                        not any([next_url.startswith(skipped) for skipped in
                                 DO_NOT_GO_TO_PLACES_STARTING_WITH])):
                    if (lev == 0) or ((lev % mlink) != 0) or (
                            ftext in node.string.lower()):
                        self.follow(next_url, fld, lev=lev + 1, verb=verb)

    @staticmethod
    def _guess_filename(get_request, url):
        if CONT_DISP in get_request.headers:
            return F_PAT.findall(get_request.headers[CONT_DISP])[0]
        return url.split("/")[-1]


if __name__ == "__main__":
    wordsegment.load()
    inv = Inventory()
    [inv.get_year(node) for top_page in TOP_PAGES for node in
     BeautifulSoup(requests.get(top_page).text, 'html.parser').find_all('a')
     if node and node.string]