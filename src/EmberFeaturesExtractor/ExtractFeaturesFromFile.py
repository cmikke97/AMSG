import json  # JSON encoder and decoder
import os  # Provides a portable way of using operating system dependent functionality

import baker  # Easy, powerful access to Python functions from the command line
import numpy as np  # The fundamental package for scientific computing with Python
from logzero import logger  # Robust and effective logging for Python

import vt
import requests

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

    if not os.path.exists(binary_path):
        logger.error("{} does not exist".format(binary_path))
        return

    logger.info("Opening file {}".format(binary_path))
    file_data = open(binary_path, "rb").read()

    logger.info("Extracting features")
    extractor = PEFeatureExtractor(feature_version, print_feature_warning=print_warnings)

    raw_features = extractor.raw_features(file_data)
    raw_features_json = json.dumps(raw_features)

    with open(raw_features_dest_file, "a") as raw_file:
        raw_file.write(raw_features_json)

    features = np.array(extractor.feature_vector(file_data), dtype=np.float32)

    logger.info("Feature vector")
    print(features)


@baker.command
def retrieve_sample_family_info(raw_features_file,
                                vt_key):

    with open(raw_features_file, "r+") as fin:
        for raw_object in fin:
            raw_features = json.loads(raw_object)
            sha = raw_features["sha256"]

            client = vt.Client(vt_key)

            file = client.get_object("/files/" + sha)

            #file.first_submission_date


class MalwareBazaarAPI:

    def __init__(self):
        self.api_errors = {"http_post_expected": "The API expected a HTTP POST request",
                           "tag_not_found": "The tag you wanted to query is unknown to MalwareBazaar",
                           "illegal_tag": "No valid tag provided",
                           "no_tag_provided": "You did not provide a tag",
                           "no_results": "Your query yield no results"}

    def query_tag(self,
                  tag,
                  amount=10):

        data = {
            'query': 'get_taginfo',
            'tag': str(tag),
            'limit': str(amount),
        }

        response = requests.post('https://mb-api.abuse.ch/api/v1/', data=data, timeout=15)
        json_response = json.loads(response.content.decode("utf-8", "ignore"))

        query_status = json_response['query_status']
        if query_status in self.api_errors.keys():
            logger.error(self.api_errors[query_status])
            return

        malware_list = json_response['data']

        logger.info("Found {} results for tag {}".format(len(malware_list), tag))
        for malware_info in malware_list['data']:
            print(malware_info)


@baker.command
def download_malware_samples(tag,
                             amount=10):

    MalwareBazaarAPI.query_tag(tag, amount)


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
