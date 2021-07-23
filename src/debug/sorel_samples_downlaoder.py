import json
import multiprocessing
import os  # provides a portable way of using operating system dependent functionality
import time
from multiprocessing.pool import ThreadPool

import baker  # easy, powerful access to Python functions from the command line
from logzero import logger  # robust and effective logging for Python
from tqdm import tqdm
import zlib

from emberFeatures.features import PEFeatureExtractor
from emberFeatures.vectorize_features import create_vectorized_features
from utils.download_utils import BucketFileDownloader, check_files, needed_objects, objects_labels

cores = multiprocessing.cpu_count()


def download_example_samples(destination_dir):  # path to the destination folder where to save the element to
    """ Download SOREL20M dataset elements from the s3 socket and save them in the specified destination directory.

    Args:
        destination_dir: Path to the destination folder where to save the element to
    """

    # get absolute path if the one provided is relative
    if not os.path.isabs(destination_dir):
        destination_dir = os.path.abspath(destination_dir)

    # create destination dir if it does not already exist
    os.makedirs(destination_dir, exist_ok=True)

    # get dataset base absolute path
    dataset_base_path = os.path.dirname(os.path.join(destination_dir, needed_objects['binary1']))

    # check if all the needed files were already downloaded, if yes return
    if check_files(destination_dir=destination_dir):
        logger.info("Found already downloaded dataset..")
        return

    # set SOREL20M bucket name
    bucket_name = "sorel-20m"

    # instantiate bucket file downloader setting the destination dir and bucket name
    downloader = BucketFileDownloader(destination_dir, bucket_name)

    # select just the objects not already present from needed objects
    objects_to_download = {key: obj for key, obj in needed_objects.items()
                           if not os.path.exists(os.path.join(destination_dir, obj))}

    # for all objects to download
    for i, (key, obj) in enumerate(objects_to_download.items()):
        downloader(obj)

        filename = os.path.join(destination_dir, obj)

        with open(filename, 'rb') as compressed:
            dec_binary = zlib.decompress(compressed.read())
        with open(filename, 'wb') as dest_file:
            dest_file.write(dec_binary)

        logger.info("{}/{} done.".format(i + 1, len(objects_to_download)))


def extract_raw_features_unpack(args):
    return extract_raw_features(*args)


def extract_raw_features(binary_path,
                         raw_features_dest_file,
                         label,
                         feature_version=2,
                         print_warnings=False):
    logger.info("Extracting features for file {}".format(binary_path))

    # open file and read its binaries
    file_data = open(binary_path, "rb").read()

    # initialize PEFeatureExtractor
    extractor = PEFeatureExtractor(feature_version, print_feature_warning=print_warnings)

    # extract raw features from file binaries
    raw_features = extractor.raw_features(file_data)

    raw_features['label'] = label

    # dump raw features as json object
    raw_features_json = json.dumps(raw_features) + '\n'
    # open destination file and append raw features json object to it
    with open(raw_features_dest_file, 'a') as raw_file:
        raw_file.write(raw_features_json)


@baker.command
def download_and_extract_features(dataset_dest_dir):
    # crate fresh_dataset_dest_dir if it did not already exist
    os.makedirs(dataset_dest_dir, exist_ok=True)
    raw_features_dest_file = os.path.join(dataset_dest_dir, 'raw_features.json')

    # set samples_dir and metadata_dir
    downloaded_samples_dir = os.path.join(dataset_dest_dir)

    # create directories
    os.makedirs(downloaded_samples_dir, exist_ok=True)

    download_example_samples(downloaded_samples_dir)

    samples_dir = os.path.join(downloaded_samples_dir, '09-DEC-2020', 'binaries')

    # get all files inside the samples directory
    files = {samples_file: os.path.join(samples_dir, samples_file)
             for samples_file in os.listdir(samples_dir)
             if os.path.isfile(os.path.join(samples_dir, samples_file))}

    print(samples_dir)
    print(os.listdir(samples_dir))
    print(files)

    argument_iterator = ((path,
                          objects_labels[filename],
                          raw_features_dest_file) for filename, path in files.items())

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
