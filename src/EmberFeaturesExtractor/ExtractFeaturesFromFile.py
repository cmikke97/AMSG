import json  # JSON encoder and decoder
import os  # Provides a portable way of using operating system dependent functionality
import sys

import baker  # Easy, powerful access to Python functions from the command line
import numpy as np  # The fundamental package for scientific computing with Python
from logzero import logger  # Robust and effective logging for Python

import vt
import requests
import pyzipper

import multiprocessing
import pandas as pd
import tqdm

from features import PEFeatureExtractor


@baker.command
def extract_features_from_pe(binary_path,  # path to the PE file
                             raw_features_dest_file,  # where to write raw features
                             feature_version=2,  # EMBER feature version
                             print_warnings=False,  # whether to print warnings or not
                             ):
    """
    Extract EMBER features from PE file

    :param binary_path: Path to the PE file
    :param raw_features_dest_file: where to write raw features
    :param feature_version: EMBER feature version (default=2)
    :param print_warnings: whether to print warnings or not (default=False)
    """

    # if the binary path does not exist log error and exit
    if not os.path.exists(binary_path):
        logger.error("{} does not exist".format(binary_path))
        sys.exit(1)

    # log info
    logger.info("Opening file {}".format(binary_path))
    # open file and read its binaries
    file_data = open(binary_path, "rb").read()

    # log info
    logger.info("Extracting features")
    # initialize PEFeatureExtractor
    extractor = PEFeatureExtractor(feature_version, print_feature_warning=print_warnings)

    # extract raw features from file binaries
    raw_features = extractor.raw_features(file_data)
    # dump raw features as json object
    raw_features_json = json.dumps(raw_features)
    # open destination file and append raw features json object to it
    with open(raw_features_dest_file, "a") as raw_file:
        raw_file.write(raw_features_json)

    # extract feature vector from file binaries
    features = np.array(extractor.feature_vector(file_data), dtype=np.float32)

    logger.info("Feature vector")
    print(features)

    # .............................


@baker.command
def retrieve_sample_family_info(raw_features_file,
                                vt_key):
    """
    Retrieve family information for the sha256 files found in raw features file
    """

    # initialize VirusTotal client with the provided user key
    client = vt.Client(vt_key)

    # open raw features file in read-write mode
    with open(raw_features_file, "r+") as fin:
        # for each raw object (line) in the file
        for raw_object in fin:
            # load raw features from json representation
            raw_features = json.loads(raw_object)
            # get corresponding sha256 hash
            sha = raw_features["sha256"]

            # get file information from VirusTotal
            file = client.get_object("/files/" + sha)

            #file.first_submission_date

            # .................................


class MalwareBazaarAPI:
    """
    Simple Malware Bazaar API class. It implements a few methods to interact with Malware Bazaar Rest API.
    """

    def __init__(self):

        # set malware bazaar url
        self.url = 'https://mb-api.abuse.ch/api/v1/'

        # malware bazaar api errors
        self.api_errors = {
            "tag_retrieve": {
                "http_post_expected": "The API expected a HTTP POST request",
                "tag_not_found": "The tag you wanted to query is unknown to MalwareBazaar",
                "illegal_tag": "No valid tag provided",
                "no_tag_provided": "You did not provide a tag",
                "no_results": "Your query yield no results"
            },
            "signature_retrieve": {
                "http_post_expected": "The API expected a HTTP POST request",
                "signature_not_found": "The signature you wanted to query is unknown to MalwareBazaar",
                "illegal_signature	": "The text you provided is not a valid signature",
                "no_signature_provided": "You did not provide a signature",
                "no_results": "Your query yield no results"
            },
            "download": {
                "http_post_expected": "The API expected a HTTP POST request",
                "illegal_sha256_hash": "Illegal SHA256 hash provided",
                "no_sha256_hash": "No SHA256 hash provided",
                "file_not_found": "The file was not found or is unknown to MalwareBazaar"
            }
        }

    @staticmethod
    def check_sha256(s):  # (supposedly) sha256 of a malware sample

        # if s is empty just return
        if s == "":
            return

        # if the length of s is wrong raise exception
        if len(s) != 64:
            raise ValueError("Please use sha256 value instead of '" + s + "'")

        # return s as string
        return str(s)

    def query(self,
              query,  # tag/signature to retrieve metadata of
              qtype='tag',  # type of query to make; valid options are "tag" or "signature"
              amount=10):  # maximum amount of samples' metadata to retrieve
        """
        Get a list of malware samples' info (max 1'000) associated with a specific tag.
        """

        # if the query type is different from expected log error and exit
        if qtype != 'tag' and qtype != 'signature':
            logger.error('Unknown query type. Valid options are "tag" or "signature"')
            sys.exit(1)

        if qtype == 'tag':
            # define data to post to Rest API
            data = {
                'query': 'get_taginfo',  # type of action: retrieve tag metadata
                'tag': str(query),  # retrieve samples' metadata associated with this tag
                'limit': str(amount),  # get the first 'limit' samples
            }
        else:
            # define data to post to Rest API
            data = {
                'query': 'get_siginfo',  # type of action: retrieve signature metadata
                'signature': str(query),  # retrieve samples' metadata associated with this signature
                'limit': str(amount),  # get the first 'limit' samples
            }

        # send post request to Malware Bazaar Rest API and retrieve response
        response = requests.post(self.url, data=data, timeout=15)
        # decode response content and interpret it as json
        json_response = response.json()

        # get response query status
        query_status = json_response['query_status']
        # if the current query status matches one of the possible errors log error and exit
        if query_status in self.api_errors[qtype + '_retrieve'].keys():
            logger.error(self.api_errors[qtype + '_retrieve'][query_status])
            sys.exit(1)

        # get malware metadata list from response
        malware_list = json_response['data']

        # log info
        logger.info("Found {} results for {} {}".format(len(malware_list), qtype, query))

        # return malware metadata list
        return malware_list

    def retrieve_malware_sample(self,
                                sha256_hash,  # sha256 hash of the malware sample to retrieve
                                dest_dir,  # destination directory where to save file
                                unzip=False):  # whether to unzip downloaded file or not

        # set zip password
        ZIP_PASSWORD = b'infected'
        # set post header
        headers = {'API-KEY': ''}

        # define data to post to Rest API
        data = {
            'query': 'get_file',  # type of action: retrieve malware sample
            'sha256_hash': self.check_sha256(sha256_hash),  # sha256 of the sample to retrieve
        }

        # send post request to Malware Bazaar Rest API and retrieve response
        response = requests.post(self.url, data=data, headers=headers, timeout=15, allow_redirects=True)

        # if Malware Bazaar did not find the file log error and exit
        if 'file_not_found' in response.text:
            logger.error("Error: file not found")
            sys.exit()

        # define destination filename as a concatenation of the dest dir with the sha256 hash of the file
        filename = os.path.join(dest_dir, sha256_hash + '.zip')
        # open destination file in binary write mode and write the response content to it
        open(filename, 'wb').write(response.content)

        # if the user selected the unzip option
        if unzip:
            # open zip file through AESZipFile object of package pyzipper
            with pyzipper.AESZipFile(filename) as zf:
                # set zip file password
                zf.pwd = ZIP_PASSWORD
                # extract all members from the archive to the current working directory
                _ = zf.extractall(dest_dir)
                # log info
                logger.info("Sample \"" + sha256_hash + "\" downloaded and unpacked.")
                # return list of archive members by name
                return zf.namelist()
        else:
            # log info
            logger.info("Sample \"" + sha256_hash + "\" downloaded.")
            # return filename
            return [sha256_hash + '.zip']


@baker.command
def download_samples(query,  # tag/signature to retrieve metadata of
                     dest_dir,  # destination directory where to save file
                     qtype='tag',  # type of query to make; valid options are "tag" or "signature"
                     amount=10,  # maximum amount of samples' metadata to retrieve
                     unzip=False):  # whether to unzip downloaded file or not

    """
    Download 'amount' malware samples (and relative metadata) associated with the provided tag/signature
    from Malware Bazaar.

    :param query: Tag/Signature to retrieve metadata of
    :param dest_dir: Destination directory where to save file
    :param qtype: Type of query to make; valid options are "tag" or "signature" (default: 'tag')
    :param amount: Maximum amount of samples' metadata to retrieve
    :param unzip: Whether to unzip downloaded file or not (default: False)
    """

    # create destination directory
    os.system('mkdir -p {}'.format(dest_dir))

    # instantiate Malware Bazaar API
    api = MalwareBazaarAPI()
    # initialize list containing the names of the downloaded files
    files_downloaded = []

    # query 'amount' samples' metadata associated with tag 'tag'
    malware_list = api.query(query=query,
                             qtype=qtype,
                             amount=amount)

    # for each malware metadata in the metadata list
    for malware_info in malware_list:
        # print malware metadata
        print(malware_info)

        # retrieve malware sample and append its name to global file name list
        files_downloaded.extend(api.retrieve_malware_sample(sha256_hash=malware_info['sha256_hash'],
                                                            dest_dir=dest_dir,
                                                            unzip=unzip))


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
