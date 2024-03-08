import re
import os
import requests
import wordsegment

from bs4 import BeautifulSoup
from requests.exceptions import MissingSchema, InvalidSchema

ELECTIONS_PAGE = r"https://results.aec.gov.au/"
MAXIMUM_FILE_SIZE = 2e8

HTML_HEADER_CONTENT_TYPE_KEY = 'content-type'
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
        return True

    def fetch(self, url, folders, check_type=False,
              target_type="application/octet-stream"):
        header = requests.head(url, allow_redirects=True).headers
        if check_type:
            content_type = str(header.get(HTML_HEADER_CONTENT_TYPE_KEY)).lower()
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

    def _download_file(self, url, folders):
        get_request = requests.get(url, allow_redirects=True)
        fname = Inventory.guess_filename(get_request, url)
        if fname:
            path = os.path.join(*folders, *wordsegment.segment(fname.lower()))
            os.makedirs(path, exist_ok=True)
            with open(os.path.join(path, fname), "wb") as target_file:
                target_file.write(get_request.content)
        else:
            print(f"Didn't download {url}. Can't guess the fname.")

    @staticmethod
    def guess_filename(get_request, url):
        if CONT_DISP in get_request.headers:
            return F_PAT.findall(get_request.headers[CONT_DISP])[0]
        return url.split("/")[-1]

    def follow(self, url, folders, verbose=True, lev=0, ext='.csv',
               ftext='download'):
        if url and self(url):
            url_split_on_slashes = url.split("/")
            try:
                stem = "/".join(url_split_on_slashes[:-1])
                [self.next_node(
                    ftext, lev, node, stem, ext, verbose, folders) for node in
                    BeautifulSoup(requests.get(url).text,
                                  'html.parser').find_all('a') if node]
                if verbose:
                    print(' '.join([". " * lev, url_split_on_slashes[-1]]))
            except InvalidSchema as schemaException:
                if verbose:
                    print(f"Didn't download {url}. {str(schemaException)}")
            except MissingSchema:
                pass

    def next_node(self, ftext, lev, node, stem, ext, verbose, folders):
        node_get = node.get('href')
        if node_get:
            next_url = f"{stem}/{node_get}"
            if node.string and ftext in node.string.lower():
                self.follow(next_url, folders, lev=lev + 1, verbose=verbose)
            if node_get.endswith(ext):
                inv.fetch(next_url, folders)


if __name__ == "__main__":
    wordsegment.load()
    inv = Inventory()
    for req_node in BeautifulSoup(
            requests.get(ELECTIONS_PAGE).text, 'html.parser').find_all('a'):
        if req_node and req_node.string:
            match = FOLDERS_PATTERN.match(req_node.string.lower())
            if match:
                inv.follow(req_node.get('href'), (match.group(1), "".join([
                    char for char in match.group(2) if char.isalpha()])))
