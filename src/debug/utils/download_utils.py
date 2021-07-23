import os  # provides a portable way of using operating system dependent functionality
import threading  # constructs higher-level threading interfaces on top of the lower level _thread module
from pathlib import Path  # provide path-handling operations which don’t actually access a filesystem

import boto3  # used to create, configure, and manage AWS services (s3 included)
from tqdm import tqdm  # instantly makes loops show a smart progress meter
from botocore import UNSIGNED  # constant to use to connect to s3 bucket anonymously (botocore is the core of boto 3)
from botocore.client import Config  # advanced configuration for Botocore clients (botocore is the core of boto 3)
from logzero import logger  # robust and effective logging for Python

# dataset objects to be downloaded
needed_objects = {"binary1": "09-DEC-2020/binaries/ead8f04232362eff599d80d8217aed0b35715ca6b106827844eaffd2ca734fcb",
                  "binary2": "09-DEC-2020/binaries/a6f63923e467e6f7de21b0b1c7db6e42654eb519b27c75d0faad7a1a37c5380c",
                  "binary3": "09-DEC-2020/binaries/a91ec181dd9f41eb9a7511aebf979ae6c9947300e91b27ee4e0b0a4a719a8448",
                  "binary4": "09-DEC-2020/binaries/dd8f335a01363d2b7f4028c76d45492c458f94e690c47ac60beca9c994c7dbb1",
                  "binary5": "09-DEC-2020/binaries/75630e887e3807ea44fabe6a7f4fc5208b1ef18cadf35d54c50f60a0045b0d4a"}


class ProgressPercentage(object):
    """ Class used to display a bar indicating download progress. """

    def __init__(self,
                 pbar):  # Already initialized tqdm progress bar
        """ Init progress bar.

        Args:
            pbar: Already initialized tqdm progress bar
        """

        # set some attributes
        self.pbar = pbar
        self._lock = threading.Lock()  # instantiate lock

    def __call__(self,
                 bytes_amount):  # amount of bytes received
        """ Update progress bar.

        Args:
            bytes_amount: Amount of bytes received
        """

        # acquire lock (for thread safety)
        with self._lock:
            # update tqdm progress bar with the bytes amount
            self.pbar.update(bytes_amount)


class BucketFileDownloader(object):
    """ Class used to download bucket files from an s3 bucket. """

    def __init__(self,
                 destination_dir,  # path to the folder where to save the element to
                 bucket_name):  # name of the s3 bucket where to find the elements to download
        """ Init bucket file downloader.

        Args:
            destination_dir: Path to the folder where to save the element to
            bucket_name: Name of the s3 bucket where to find the elements to download
        """

        # set some attributes
        self._destination_dir = destination_dir
        self._bucketName = bucket_name

        # open boto3 client connection to the s3 bucket in anonymous mode
        self._s3client = boto3.client('s3', config=Config(signature_version=UNSIGNED))

    def __call__(self,
                 object_name):  # name (relative path wrt the s3 bucket) of the object to download
        """ Download single object from s3 bucket.

        Args:
            object_name: Name (relative path wrt the s3 bucket) of the object to download
        """

        # generate destination path where to save the element to
        dest_path = os.path.join(self._destination_dir, object_name)

        # create parent directory path if it does not exist (it succeeds even if the directory already exists)
        os.makedirs(Path(dest_path).parent.absolute(), exist_ok=True)

        logger.info("Now downloading {} from s3 bucket..".format(object_name))

        print(self._s3client.list_objects_v2(Bucket=self._bucketName,
                                             Prefix=object_name,
                                             MaxKeys=100))

        # retrieve metadata from the s3 object without returning the object itself
        response = self._s3client.head_object(Bucket=self._bucketName,
                                              Key=object_name)

        # extract total object size info from the response header
        size = response['ContentLength']

        # instantiate tqdm progress bar
        with tqdm(total=size) as pbar:
            # download object file using boto3 'download_file' method
            # while passing it the ProgressPercentage as callback function
            # -> its call method will be called intermittently passing it the amount of bytes received
            self._s3client.download_file(self._bucketName,
                                         object_name,
                                         dest_path,
                                         Callback=ProgressPercentage(pbar))


def check_files(destination_dir):  # path to the folder where to search for the needed files
    """ Check if the dataset needed files are already present inside the specified directory.

    Args:
        destination_dir: Path to the folder where to search for the needed files
    Returns:
        True if there are no objects to download, False otherwise.
    """

    # select just the objects not already present from the needed objects
    objects_to_download = {key: obj for key, obj in needed_objects.items()
                           if not os.path.exists(os.path.join(destination_dir, obj))}

    # if there are no objects to download return true
    return len(objects_to_download) == 0
