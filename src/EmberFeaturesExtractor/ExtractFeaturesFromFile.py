import json  # JSON encoder and decoder
import os  # Provides a portable way of using operating system dependent functionality
import sys  # System-specific parameters and functions
import tempfile

import baker  # Easy, powerful access to Python functions from the command line
import numpy as np  # The fundamental package for scientific computing with Python
import pyzipper  # A replacement for Python’s zipfile that can read and write AES encrypted zip files
import requests  # Simple HTTP library for Python
import vt  # Official Python client library for VirusTotal
from logzero import logger  # Robust and effective logging for Python

from features import PEFeatureExtractor  # Import PEFeatureExtractor from features.py

import configparser
import mlflow
from tqdm import tqdm
from time import sleep

import pandas as pd
import multiprocessing


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

        self.max_limit = 1000

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

        response = None

        while True:
            try:
                # send post request to Malware Bazaar Rest API and retrieve response
                response = requests.post(self.url, data=data, timeout=30)
                break
            except requests.Timeout:
                print("\r")
                logger.error("Connection timeout. Retrying in 30 seconds.")
                sleep(30)
                continue

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

        response = None

        while True:
            try:
                # send post request to Malware Bazaar Rest API and retrieve response
                response = requests.post(self.url, data=data, headers=headers, timeout=30, allow_redirects=True)
                break
            except requests.Timeout:
                print("\r")
                logger.error("Connection timeout. Retrying in 30 seconds.")
                sleep(30)
                continue

        # if Malware Bazaar did not find the file log error and exit
        if 'file_not_found' in response.text:
            print("\r")
            logger.error("Error: file not found")
            return None

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
                # return list of archive members by name
                namelist = zf.namelist()

            # remove zipped version
            os.remove(filename)
            # return name list
            return namelist
        else:
            # return filename
            return [sha256_hash + '.zip']


def raw_feature_iterator(file_paths):
    """
    Yield raw feature strings from the inputed file paths
    """
    for path in file_paths:
        with open(path, "r") as fin:
            for line in fin:
                yield line


def vectorize(irow, raw_features_string, X_path, y_path, extractor, nrows):
    """
    Vectorize a single sample of raw features and write to a large numpy file
    """
    raw_features = json.loads(raw_features_string)
    feature_vector = extractor.process_raw_features(raw_features)

    y = np.memmap(y_path, dtype=np.float32, mode="r+", shape=nrows)
    y[irow] = raw_features["label"]

    X = np.memmap(X_path, dtype=np.float32, mode="r+", shape=(nrows, extractor.dim))
    X[irow] = feature_vector


def vectorize_unpack(args):
    """
    Pass through function for unpacking vectorize arguments
    """
    return vectorize(*args)


def vectorize_subset(X_path, y_path, raw_feature_paths, extractor, nrows):
    """
    Vectorize a subset of data and write it to disk
    """
    # Create space on disk to write features to
    X = np.memmap(X_path, dtype=np.float32, mode="w+", shape=(nrows, extractor.dim))
    y = np.memmap(y_path, dtype=np.float32, mode="w+", shape=nrows)
    del X, y

    # Distribute the vectorization work
    pool = multiprocessing.Pool()
    argument_iterator = ((irow, raw_features_string, X_path, y_path, extractor, nrows)
                         for irow, raw_features_string in enumerate(raw_feature_iterator(raw_feature_paths)))
    for _ in tqdm.tqdm(pool.imap_unordered(vectorize_unpack, argument_iterator), total=nrows):
        pass


def create_vectorized_features(data_dir, feature_version=2):
    """
    Create feature vectors from raw features and write them to disk
    """
    extractor = PEFeatureExtractor(feature_version)

    print("Vectorizing training set")
    X_path = os.path.join(data_dir, "X_train.dat")
    y_path = os.path.join(data_dir, "y_train.dat")
    raw_feature_paths = [os.path.join(data_dir, "train_features_{}.jsonl".format(i)) for i in range(6)]
    nrows = sum([1 for fp in raw_feature_paths for line in open(fp)])
    vectorize_subset(X_path, y_path, raw_feature_paths, extractor, nrows)

    print("Vectorizing test set")
    X_path = os.path.join(data_dir, "X_test.dat")
    y_path = os.path.join(data_dir, "y_test.dat")
    raw_feature_paths = [os.path.join(data_dir, "test_features.jsonl")]
    nrows = sum([1 for fp in raw_feature_paths for line in open(fp)])
    vectorize_subset(X_path, y_path, raw_feature_paths, extractor, nrows)


def read_vectorized_features(data_dir, subset=None, feature_version=2):
    """
    Read vectorized features into memory mapped numpy arrays
    """
    if subset is not None and subset not in ["train", "test"]:
        return None

    extractor = PEFeatureExtractor(feature_version)
    ndim = extractor.dim
    X_train = None
    y_train = None
    X_test = None
    y_test = None

    if subset is None or subset == "train":
        X_train_path = os.path.join(data_dir, "X_train.dat")
        y_train_path = os.path.join(data_dir, "y_train.dat")
        y_train = np.memmap(y_train_path, dtype=np.float32, mode="r")
        N = y_train.shape[0]
        X_train = np.memmap(X_train_path, dtype=np.float32, mode="r", shape=(N, ndim))
        if subset == "train":
            return X_train, y_train

    if subset is None or subset == "test":
        X_test_path = os.path.join(data_dir, "X_test.dat")
        y_test_path = os.path.join(data_dir, "y_test.dat")
        y_test = np.memmap(y_test_path, dtype=np.float32, mode="r")
        N = y_test.shape[0]
        X_test = np.memmap(X_test_path, dtype=np.float32, mode="r", shape=(N, ndim))
        if subset == "test":
            return X_test, y_test

    return X_train, y_train, X_test, y_test


def download_samples(query,  # tag/signature to retrieve metadata of
                     dest_dir,  # destination directory where to save file
                     metadata_file_path,  # file where to save samples metadata
                     qtype='signature',  # type of query to make; valid options are "tag" or "signature"
                     amount=10,  # amount of samples' metadata to retrieve (default:10, max: 999)
                     unzip=False):  # whether to unzip downloaded file or not

    """
    Download 'amount' malware samples (and relative metadata) associated with the provided tag/signature
    from Malware Bazaar.

    :param query: Tag/Signature to retrieve metadata of
    :param dest_dir: Destination directory where to save file
    :param metadata_file_path: File where to save samples metadata
    :param qtype: Type of query to make; valid options are "tag" or "signature" (default: 'tag')
    :param amount: Amount of samples' metadata to retrieve (default:10, max: 999)
    :param unzip: Whether to unzip downloaded file or not (default: False)
    """

    logger.info("Retrieving samples metadata for family '{}'...".format(query))

    # instantiate Malware Bazaar API
    api = MalwareBazaarAPI()
    # initialize list of found pe files of the specified family
    pe_file_list = []
    # initialize list containing the names of the downloaded files
    files_downloaded = []

    # initialize current_amount of samples to query from malware bazaar as the amount provided (clipped to api maxlimit)
    current_amount = amount if amount < api.max_limit else api.max_limit - 1
    # until current amount is less than the maximum allowed by the api
    while current_amount < api.max_limit:
        # multiply current amount by 2 (clipping the result to api maxlimit)
        current_amount = current_amount * 2 if current_amount * 2 <= api.max_limit else api.max_limit

        # query 'amount' samples' metadata associated with tag 'tag'
        malware_list = api.query(query=query,
                                 qtype=qtype,
                                 amount=current_amount)

        # get only the metadata of PE files from the list
        # (check file type or, it the file type is unknown, check the file name extension)
        pe_file_list.extend([m for m in malware_list
                             if m['file_type'] == 'exe' or m['file_name'].split('.')[-1] == 'exe'])

        logger.info("Got {} samples; {} of them where PE files.".format(len(malware_list), len(pe_file_list)))

        # if the amount of found pe files is greater than the required one, break; otherwise retry with a bigger
        # current_amount
        if len(pe_file_list) >= amount:
            break

    # finally if the amount of found pe files is still less than required, provide a warning and return false
    if len(pe_file_list) < amount:
        logger.warning("Found only {} PE malware samples between the ones retrieved. Ignoring family {}.."
                       .format(len(pe_file_list), query))
        return False

    i = 0
    # open metadata file
    with open(metadata_file_path, 'r+') as metadata_file:
        # load existing data into a dict
        metadata = json.load(metadata_file)

        with tqdm(total=amount) as pbar:
            pbar.set_description("Downloading samples for family '{}'".format(query))
            # for each malware metadata in the pe metadata list
            for malware_info in pe_file_list:
                # if we downloaded 'amount' malware samples for this family, break
                if i >= amount:
                    break

                # retrieve malware sample
                downloaded_name = api.retrieve_malware_sample(sha256_hash=malware_info['sha256_hash'],
                                                              dest_dir=dest_dir,
                                                              unzip=unzip)

                # if downloaded malware sample name is None -> the file could not be found on Malware Bazaar, ignore it
                if downloaded_name is not None:

                    # set data to write to file
                    new_data = {malware_info['sha256_hash']: malware_info}
                    # join new_data with metadata
                    metadata.update(new_data)

                    # append malware sample name to global file name list
                    files_downloaded.extend(downloaded_name)

                    # update i
                    i += 1

                    pbar.update(1)

        if i < amount:
            return False

        # set file's current position at offset
        metadata_file.seek(0)
        # convert back to json
        json.dump(metadata, metadata_file)

    # if we manage to download exactly 'amount' samples for the current family log files downloaded as text
    # and then return true
    mlflow.log_text("{}".format('\n'.join(sample for sample in files_downloaded)),
                    "downloaded_{}_samples.txt".format(query))

    return True


def extract_raw_features(binary_path,  # path to the PE file
                         raw_features_dest_file,  # where to write raw features
                         label,  # family label
                         feature_version=2,  # EMBER feature version
                         print_warnings=False):  # whether to print warnings or not
    """
    Extract EMBER features from PE file
    :param binary_path: Path to the PE file
    :param raw_features_dest_file: where to write raw features
    :param label: Family label
    :param feature_version: EMBER feature version (default=2)
    :param print_warnings: whether to print warnings or not (default=False)
    """

    logger.info("Extracting features for file {}".format(binary_path))

    # open file and read its binaries
    file_data = open(binary_path, "rb").read()

    # initialize PEFeatureExtractor
    extractor = PEFeatureExtractor(feature_version, print_feature_warning=print_warnings)

    # extract raw features from file binaries
    raw_features = extractor.raw_features(file_data)

    # set sample's label
    raw_features['label'] = label

    # dump raw features as json object
    raw_features_json = json.dumps(raw_features)
    # open destination file and append raw features json object to it
    with open(raw_features_dest_file, 'a') as raw_file:
        raw_file.write(raw_features_json)


@baker.command
def build_fresh_dataset(config_file,  # config file path
                        raw_features_dest_path):  # where to write raw features
    """
    Build fresh dataset retrieving samples from Malware Bazaar given a list of family signatures stored in a
    configuration file.

    :param config_file: Config file path
    :param raw_features_dest_path: Where to write raw features
    """

    # start run
    with mlflow.start_run() as mlrun:
        # instantiate config parser and read config file
        config = configparser.ConfigParser()
        config.read(config_file)

        # get family signatures (and their label representation) to retrieve from config file
        signatures = [sig.lower() for sig in config['featureExtractor']['signatures'].split(",")]
        # get the number of families to consider between the ones provided from config file
        number_of_families = int(config['featureExtractor']['number_of_families'])
        # get amount of samples to retrieve for each family from config file
        amount_each = int(config['featureExtractor']['amount_each'])

        # log some params
        mlflow.log_param("amount_each", amount_each)
        mlflow.log_param("number_of_families", number_of_families)

        # crate raw_features_dest_path if it did not already exist
        os.makedirs(raw_features_dest_path, exist_ok=True)

        # compute raw features destination file
        raw_features_dest_file = os.path.join(raw_features_dest_path, "raw_features.json")

        # initialize sig - label dictionary
        sig_to_label = {}

        # create temporary directory
        with tempfile.TemporaryDirectory() as tempdir:
            # set samples_dir and metadata_dir
            samples_dir = os.path.join(tempdir, "samples")
            metadata_dir = os.path.join(tempdir, "metadata")
            metadata_file_path = os.path.join(metadata_dir, 'metadata.json')

            # create directories
            os.makedirs(samples_dir, exist_ok=True)
            os.makedirs(metadata_dir, exist_ok=True)

            # write empty json object to file (in preparation for download)
            with open(metadata_file_path, "w") as json_:
                json.dump({}, json_)

            i = 0
            # for each of the first 'number_of_families' signatures
            for sig in signatures:
                # if we successfully downloaded 'amount' samples for 'number_of_families' families, break
                if i >= number_of_families:
                    break

                logger.info("Considering now family {}. {}/{}".format(sig, i + 1, number_of_families))

                # download 'amount_each' samples, if the download was successful update i, otherwise ignore family
                # and go on
                if download_samples(query=sig,
                                    dest_dir=samples_dir,
                                    metadata_file_path=metadata_file_path,
                                    qtype='signature',
                                    amount=amount_each,
                                    unzip=True):

                    sig_to_label[sig] = i
                    i += 1

            # log used signatures
            mlflow.log_text("{}".format('\n'.join(str(sig) for sig in sig_to_label.keys())), "family_signatures.txt")

            # dump sig_to_label dictionary to temporary file and then log file
            sig_to_label_path = os.path.join(tempdir, "sig_to_label.json")
            with open(sig_to_label_path, 'w') as sig_to_label_file:
                json.dump(sig_to_label, sig_to_label_file)

            mlflow.log_artifact(sig_to_label_path, ".")

            # get all files inside the samples directory
            files = {f: os.path.join(samples_dir, f) for f in os.listdir(samples_dir)
                     if os.path.isfile(os.path.join(samples_dir, f))}

            # open metadata file
            with open(metadata_file_path, "r") as metadata_file:
                # read metadata file
                metadata = json.load(metadata_file)

                # for all files
                for filename, path in files.items():
                    # get PE file sha256 from filename
                    sha = filename.split('.')[0]

                    # get current file metadata
                    current_file_meta = metadata[sha]
                    # get current file label
                    label = sig_to_label[current_file_meta['signature'].lower()]

                    # extract PE file raw features
                    extract_raw_features(binary_path=path,
                                         raw_features_dest_file=raw_features_dest_file,
                                         label=label)

            # log metadata file
            mlflow.log_artifact(metadata_file_path, "metadata")


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
