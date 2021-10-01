# Copyright 2021, Crepaldi Michele.
#
# Developed as a thesis project at the TORSEC research group of the Polytechnic of Turin (Italy) under the supervision
# of professor Antonio Lioy and engineer Andrea Atzeni and with the support of engineer Andrea Marcelli.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
# an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.

import configparser  # implements a basic configuration language for Python programs
import json  # json encoder and decoder
import multiprocessing  # supports spawning processes using an API similar to the threading module
import os  # provides a portable way of using operating system dependent functionality
import sys  # system-specific parameters and functions
import tempfile  # used to create temporary files and directories
from multiprocessing.pool import ThreadPool  # pool of worker threads jobs can be submitted to

import baker  # easy, powerful access to Python functions from the command line
import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
from logzero import logger  # robust and effective logging for Python
from tqdm import tqdm  # instantly makes loops show a smart progress meter

from emberFeatures.features import PEFeatureExtractor
from emberFeatures.vectorize_features import create_vectorized_features
from utils.malware_bazaar_api import MalwareBazaarAPI

cores = multiprocessing.cpu_count()
# instantiate Malware Bazaar API
api = MalwareBazaarAPI()

# get config file path
fresh_dataset_builder_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(fresh_dataset_builder_dir)
config_filepath = os.path.join(src_dir, 'config.ini')

# instantiate config parser and read config file
config = configparser.ConfigParser()
config.read(config_filepath)

# get families (and their label representation) to retrieve from config file
families = [sig.lower().strip() for sig in config['freshDataset']['families'].split(",")]
# get the number of families to consider between the ones provided from config file
number_of_families = int(config['freshDataset']['number_of_families'])
# get amount of samples to retrieve for each family from config file
amount_each = int(config['freshDataset']['amount_each'])


def retrieve_malware_sample(args):  # retrieve malware samples arguments
    """ Pass through function for unpacking retrieve malware samples arguments.

    Args:
        args: Retrieve malware samples arguments
    Returns:
        One single malware sample.
    """

    # unpack arguments
    sha256_hash, dest_dir, unzip = args

    # query sample's metadata associated to hash 'sample['sha256_hash']'
    query_result = api.query(query=sha256_hash, qtype='hash')

    if query_result is None:
        return None, None

    downloaded_names = api.retrieve_malware_sample(sha256_hash=sha256_hash,
                                                   dest_dir=dest_dir,
                                                   unzip=unzip)

    # retrieve one single malware sample
    return query_result[0], downloaded_names


def download_and_extract(available_data,
                         family,  # family to retrieve metadata of
                         label,
                         dest_dir,  # destination directory where to save files
                         metadata_file_path,  # file where to save samples metadata
                         raw_features_dest_file,
                         amount=10,  # amount of samples' metadata to retrieve
                         unzip=False):  # whether to unzip downloaded file or not

    """ Download 'amount' malware samples (and relative metadata) associated with the provided tag/signature
    from Malware Bazaar.

    Args:
        available_data:
        family: Family to retrieve metadata of
        label:
        dest_dir: Destination directory where to save file
        metadata_file_path: File where to save samples metadata
        raw_features_dest_file:
        amount: Amount of samples' metadata to retrieve
        unzip: Whether to unzip downloaded file or not (default: False)
    Returns:
        True if it managed to download exactly 'amount' samples for the current family, False otherwise.
    """

    logger.info("Retrieving samples metadata for family '{}'...".format(family))

    available_samples_shas = [sample['sha256_hash'] for sample in available_data[family]]

    if len(available_samples_shas) < amount:
        logger.warning("Found only {} PE malware samples. Ignoring family '{}'.."
                       .format(available_samples_shas, family))
        return False

    # initialize list containing the names of the downloaded files
    files_downloaded = []

    i = 0
    # open metadata file
    with open(metadata_file_path, 'r+') as metadata_file:
        # load existing data into a dict
        metadata = json.load(metadata_file)

        # instantiate download arguments iterator getting info from the first 'amount' files in 'pe_file_list'
        argument_iterator = ((sha, dest_dir, unzip) for sha in available_samples_shas)

        # prepare progress bar
        with tqdm(total=amount) as pbar:
            pbar.set_description("Downloading samples and extracting features for family '{}'".format(family))

            # instantiate thread-pool with a number of threads equal to 'cores'
            with ThreadPool(2 * cores) as pool:

                # launch parallel downloading processes (for each malware metadata in the pe metadata list)
                for malware_info, downloaded_names in pool.imap_unordered(retrieve_malware_sample, argument_iterator):
                    # if we downloaded 'amount' malware samples for this family, break
                    if i >= amount:
                        break

                    # if downloaded malware sample name is None -> the file could not be found on Malware Bazaar,
                    # ignore it
                    if downloaded_names is not None and extract_raw_features(
                            os.path.join(dest_dir, downloaded_names[0]),
                            raw_features_dest_file,
                            label):
                        # set data to write to file
                        new_data = {malware_info['sha256_hash']: malware_info}
                        # join new_data with metadata
                        metadata.update(new_data)

                        # append malware sample name to global file name list
                        files_downloaded.append(downloaded_names[0])

                        # update i
                        i += 1

                        # update tqdm progress bar
                        pbar.update(1)

                pool.terminate()
                pool.join()

        # if the amount of malware samples for this family downloaded is less than required, return false
        if i < amount:
            return False

        # set file's current position at offset
        metadata_file.seek(0)
        # convert back to json
        json.dump(metadata, metadata_file)

    # if we manage to download exactly 'amount' samples for the current family log files downloaded as text
    # and then return true
    mlflow.log_text("{}".format('\n'.join(sample for sample in files_downloaded)),
                    str(os.path.join("downloaded_samples", "downloaded_{}_samples.txt".format(family))))

    return True


def extract_raw_features(binary_path,  # path to the PE file
                         raw_features_dest_file,  # where to write raw features
                         label,  # family label
                         feature_version=2,  # EMBER feature version
                         print_warnings=False):  # whether to print warnings or not
    """ Extract EMBER features from PE file.

    Args:
        binary_path: Path to the PE file
        raw_features_dest_file: Where to write raw features
        label: Family label
        feature_version: EMBER feature version (default: 2)
        print_warnings: Whether to print warnings or not (default: False)
    """

    # logger.info("Extracting features for file {}".format(binary_path))

    # open file and read its binaries
    file_data = open(binary_path, "rb").read()

    # initialize PEFeatureExtractor
    extractor = PEFeatureExtractor(feature_version, print_feature_warning=print_warnings)

    # extract raw features from file binaries
    raw_features = extractor.raw_features(file_data)

    if raw_features is None:
        return False

    # set sample's label
    raw_features['label'] = label

    # dump raw features as json object
    raw_features_json = json.dumps(raw_features) + '\n'
    # open destination file and append raw features json object to it
    with open(raw_features_dest_file, 'a') as raw_file:
        raw_file.write(raw_features_json)

    return True


@baker.command
def build_fresh_dataset(dataset_dest_dir):  # dir where to write the newly created dataset
    """ Build fresh dataset retrieving samples from Malware Bazaar given a list of  malware families stored in a
    configuration file.

    Args:
        dataset_dest_dir: Dir where to write the newly created dataset
    """

    # start run
    with mlflow.start_run():
        # log some params
        mlflow.log_param("amount_each", amount_each)
        mlflow.log_param("number_of_families", number_of_families)

        # crate fresh_dataset_dest_dir if it did not already exist
        os.makedirs(dataset_dest_dir, exist_ok=True)
        raw_features_dest_file = os.path.join(dataset_dest_dir, 'raw_features.json')
        sig_to_label_file = os.path.join(dataset_dest_dir, 'sig_to_label.json')

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

            available_samples_dict = api.get_full_data_dump(tempdir, families)

            i = 0
            # for each of the first 'number_of_families' families
            for fam in families:
                # if we successfully downloaded 'amount' samples for 'number_of_families' families, break
                if i >= number_of_families:
                    break

                logger.info("Considering now family '{}'. {}/{}".format(fam, i + 1, number_of_families))

                # download 'amount_each' samples, if the download was successful update i, otherwise ignore family
                # and go on
                if download_and_extract(available_data=available_samples_dict,
                                        family=fam,
                                        label=i,
                                        dest_dir=samples_dir,
                                        metadata_file_path=metadata_file_path,
                                        raw_features_dest_file=raw_features_dest_file,
                                        amount=amount_each,
                                        unzip=True):
                    sig_to_label[fam] = i
                    i += 1

            # if the number of successful family downloads is less than the required amount, exit
            if i < number_of_families:
                logger.error("It was not possible to get {} samples for {} different families.\n"
                             "Try adding more families in the config file.".format(amount_each, number_of_families))
                sys.exit(1)

            # log used families
            mlflow.log_text("{}".format('\n'.join("{}: {}".format(str(sig), i) for sig, i in sig_to_label.items())),
                            "families.txt")

            # log metadata file
            mlflow.log_artifact(metadata_file_path, "metadata")

            # dump sig_to_label dictionary to file
            with open(sig_to_label_file, 'w') as sig_to_label_file:
                json.dump(sig_to_label, sig_to_label_file)

        # create list of files containing features (there is only one in this case)
        raw_features_paths = [raw_features_dest_file]
        # create features and labels vectors from raw features
        create_vectorized_features(dataset_dest_dir=dataset_dest_dir, raw_features_paths=raw_features_paths)


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
