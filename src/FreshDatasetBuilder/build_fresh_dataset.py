import configparser  # implements a basic configuration language for Python programs
import json  # json encoder and decoder
import multiprocessing  # supports spawning processes using an API similar to the threading module
import os  # provides a portable way of using operating system dependent functionality
import sys  # system-specific parameters and functions
import tempfile  # used to create temporary files and directories
from multiprocessing.pool import ThreadPool  # pool of worker threads jobs can be submitted to
from urllib import parse  # standard interface to break Uniform Resource Locator (URL) in components

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
families = [sig.lower() for sig in config['freshDataset']['families'].split(",")]
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
    malware_info, sha256_hash, dest_dir, unzip = args

    # retrieve one single malware sample
    return malware_info, api.retrieve_malware_sample(sha256_hash=sha256_hash,
                                                     dest_dir=dest_dir,
                                                     unzip=unzip)


def download_samples(query,  # tag/signature to retrieve metadata of
                     dest_dir,  # destination directory where to save file
                     metadata_file_path,  # file where to save samples metadata
                     qtype='signature',  # type of query to make; valid options are "tag" or "signature"
                     amount=10,  # amount of samples' metadata to retrieve (default:10, max: 999)
                     unzip=False):  # whether to unzip downloaded file or not

    """ Download 'amount' malware samples (and relative metadata) associated with the provided tag/signature
    from Malware Bazaar.

    Args:
        query: Tag/Signature to retrieve metadata of
        dest_dir: Destination directory where to save file
        metadata_file_path: File where to save samples metadata
        qtype: Type of query to make; valid options are "tag" or "signature" (default: 'tag')
        amount: Amount of samples' metadata to retrieve (default:10, max: 999)
        unzip: Whether to unzip downloaded file or not (default: False)
    Returns:
        True if it managed to download exactly 'amount' samples for the current family, False otherwise.
    """

    logger.info("Retrieving samples metadata for family '{}'...".format(query))

    # initialize list of found pe files of the specified family
    pe_file_list = []
    # initialize list containing the names of the downloaded files
    files_downloaded = []

    # query 'api.max_limit' samples' metadata associated with tag 'tag'
    malware_list = api.query(query=query,
                             qtype=qtype,
                             amount=api.max_limit)

    # if there was an error (for example the query yield no results), return False and consider next signature
    if malware_list is None:
        return False

    # get only the metadata of PE files from the list
    # (check file type or, it the file type is unknown, check the file name extension)
    pe_file_list.extend([m for m in malware_list if m['file_type'] == 'exe' or m['file_name'].split('.')[-1] == 'exe'])

    logger.info("Got {} samples; {} of them where PE files.".format(len(malware_list), len(pe_file_list)))

    # if the amount of found pe files is less than required, provide a warning and return false
    if len(pe_file_list) < amount:
        logger.warning("Found only {} PE malware samples between the ones retrieved. Ignoring family '{}'.."
                       .format(len(pe_file_list), query))
        return False

    i = 0
    # open metadata file
    with open(metadata_file_path, 'r+') as metadata_file:
        # load existing data into a dict
        metadata = json.load(metadata_file)

        # instantiate download arguments iterator getting info from the first 'amount' files in 'pe_file_list'
        argument_iterator = ((malware_info, malware_info['sha256_hash'], dest_dir, unzip)
                             for malware_info in pe_file_list)

        # prepare progress bar
        with tqdm(total=amount) as pbar:
            pbar.set_description("Downloading samples for family '{}'".format(query))

            # instantiate thread-pool with a number of threads equal to 'cores'
            with ThreadPool(cores) as pool:

                # launch parallel downloading processes (for each malware metadata in the pe metadata list)
                for malware_info, downloaded_name in pool.imap_unordered(retrieve_malware_sample, argument_iterator):
                    # if we downloaded 'amount' malware samples for this family, break
                    if i >= amount:
                        break

                    # if downloaded malware sample name is None -> the file could not be found on Malware Bazaar,
                    # ignore it
                    if downloaded_name is not None:
                        # set data to write to file
                        new_data = {malware_info['sha256_hash']: malware_info}
                        # join new_data with metadata
                        metadata.update(new_data)

                        # append malware sample name to global file name list
                        files_downloaded.extend(downloaded_name)

                        # update i
                        i += 1

                        # update tqdm progress bar
                        pbar.update(1)

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
                    str(os.path.join("downloaded_samples", "downloaded_{}_samples.txt".format(query))))

    return True


def extract_raw_features_unpack(args):  # extract_raw_features arguments
    """ Pass through function for unpacking extract_raw_features arguments.

    Args:
        args: Extract_raw_features arguments
    Returns:
        Single file raw features.
    """

    # extract single file raw features
    return extract_raw_features(*args)


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

    # set sample's label
    raw_features['label'] = label

    # dump raw features as json object
    raw_features_json = json.dumps(raw_features) + '\n'
    # open destination file and append raw features json object to it
    with open(raw_features_dest_file, 'a') as raw_file:
        raw_file.write(raw_features_json)


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

            i = 0
            # for each of the first 'number_of_families' families
            for fam in families:
                # if we successfully downloaded 'amount' samples for 'number_of_families' families, break
                if i >= number_of_families:
                    break

                logger.info("Considering now family '{}'. {}/{}".format(fam, i + 1, number_of_families))

                # download 'amount_each' samples, if the download was successful update i, otherwise ignore family
                # and go on
                if download_samples(query=fam,
                                    dest_dir=samples_dir,
                                    metadata_file_path=metadata_file_path,
                                    qtype='signature',
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

            # get downloaded samples dir from current run
            downloaded_samples_dir = parse.unquote(parse.urlparse(os.path.join(mlflow.get_artifact_uri(),
                                                                               "downloaded_samples")).path)

            # get all files inside the samples directory
            files = {f.replace('\n', ''): os.path.join(samples_dir, f.replace('\n', ''))
                     for samples_file in os.listdir(downloaded_samples_dir)
                     for f in open(os.path.join(downloaded_samples_dir, samples_file), 'r')
                     if os.path.isfile(os.path.join(samples_dir, f.replace('\n', '')))}

            # open metadata file
            with open(metadata_file_path, "r") as metadata_file:
                # read metadata file
                metadata = json.load(metadata_file)

                # instantiate download arguments iterator getting info from the first 'amount' files in 'pe_file_list'
                argument_iterator = ((path,
                                      raw_features_dest_file,
                                      # get PE file sha256 from filename, then use it to get the current file metadata,
                                      # finally extract signature from file metadata and get current file label
                                      sig_to_label[metadata[filename.split('.')[0]]['signature'].lower()])
                                     for filename, path in files.items())

                # instantiate thread-pool with a number of threads equal to 'cores'
                with ThreadPool(cores) as pool:
                    # for all files, extract PE file raw features
                    for _ in tqdm(pool.imap_unordered(extract_raw_features_unpack, argument_iterator),
                                  total=len(files.items()),
                                  desc="Extracting features"):
                        pass

        # create list of files containing features (there is only one in this case)
        raw_features_paths = [raw_features_dest_file]
        # create features and labels vectors from raw features
        create_vectorized_features(dataset_dest_dir=dataset_dest_dir, raw_features_paths=raw_features_paths)


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
