import configparser
import json  # JSON encoder and decoder
import os  # Provides a portable way of using operating system dependent functionality
import sys
import tempfile

import baker  # Easy, powerful access to Python functions from the command line
import mlflow
from logzero import logger  # Robust and effective logging for Python
from tqdm import tqdm

from features import PEFeatureExtractor  # Import PEFeatureExtractor from features.py
from malware_bazaar_api import MalwareBazaarAPI
from vectorize_features import create_vectorized_features


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
    Extract EMBER features from PE file.

    :param binary_path: Path to the PE file
    :param raw_features_dest_file: where to write raw features
    :param label: Family label
    :param feature_version: EMBER feature version (default=2)
    :param print_warnings: whether to print warnings or not (default=False)
    """

    # logger.info("Extracting features for file {}".format(binary_path))

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
                        dataset_dest_dir,  # dir where to write the newly created dataset
                        sig_to_label_dir):  # dir where to save the family signature - label correspondence
    """
    Build fresh dataset retrieving samples from Malware Bazaar given a list of family signatures stored in a
    configuration file.

    :param config_file: Config file path
    :param dataset_dest_dir: Dir where to write the newly created dataset
    :param sig_to_label_dir: Dir where to save the family signature - label correspondence
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

        # crate fresh_dataset_dest_dir if it did not already exist
        os.makedirs(dataset_dest_dir, exist_ok=True)
        raw_features_dest_file = os.path.join(dataset_dest_dir, 'raw_features.json')

        # crate sig_to_label_dir if it did not already exist
        os.makedirs(sig_to_label_dir, exist_ok=True)
        sig_to_label_file = os.path.join(sig_to_label_dir, 'sig_to_label.json')

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

            # if the number of successful family downloads is less than the required amount, exit
            if i < number_of_families:
                logger.error("It was not possible to get {} samples for {} different families.\n"
                             "Try adding more signatures in the config file.".format(amount_each, number_of_families))
                sys.exit(1)

            # log used signatures
            mlflow.log_text("{}".format('\n'.join("{}: {}".format(str(sig), i) for sig, i in sig_to_label.items())),
                            "family_signatures.txt")

            # dump sig_to_label dictionary to file
            with open(sig_to_label_file, 'w') as sig_to_label_file:
                json.dump(sig_to_label, sig_to_label_file)

            # get all files inside the samples directory
            files = {f: os.path.join(samples_dir, f) for f in os.listdir(samples_dir)
                     if os.path.isfile(os.path.join(samples_dir, f))}

            # open metadata file
            with open(metadata_file_path, "r") as metadata_file:
                # read metadata file
                metadata = json.load(metadata_file)

                # for all files
                for filename, path in tqdm(files.items(), total=len(files.items()), desc="Extracting features"):
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

        # create dataset_dest_dir if it did not already exist
        os.makedirs(dataset_dest_dir, exist_ok=True)

        # create features and labels vectors from raw features
        create_vectorized_features(dataset_dest_dir)


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
