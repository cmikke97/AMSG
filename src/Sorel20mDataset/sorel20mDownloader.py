import os  # Provides a portable way of using operating system dependent functionality
import threading  # Constructs higher-level threading interfaces on top of the lower level _thread module
# offers classes representing filesystem paths with semantics appropriate for different operating systems
from pathlib import Path

import baker  # Easy, powerful access to Python functions from the command line
import boto3  # Used to create, configure, and manage AWS services (s3 included)
import mlflow
import requests
import tqdm  # Instantly makes loops show a smart progress meter
# constant to use to connect to s3 bucket anonymously (botocore is the Low-level, data-driven core of boto 3)
from botocore import UNSIGNED
# Advanced configuration for Botocore clients (botocore is the Low-level, data-driven core of boto 3)
from botocore.client import Config
from logzero import logger  # Robust and effective logging for Python


needed_objects = {"meta": "09-DEC-2020/processed-data/meta.db",
                  "lock": "09-DEC-2020/processed-data/ember_features/lock.mdb",
                  "data": "09-DEC-2020/processed-data/ember_features/data.mdb",
                  "missing": "09-DEC-2020/processed-data/shas_missing_ember_features.json"}


def _check_files(destination_dir):  # path to the destination folder where to save the element to

    # select just the objects not already present
    objects_to_download = {key: obj for key, obj in needed_objects.items()
                           if not os.path.exists(os.path.join(destination_dir, obj))}

    # if there are no objects to download return true
    return len(objects_to_download) == 0


class ProgressPercentage(object):
    """class used to display a bar indicating download progress"""

    def __init__(self,
                 pbar):  # tqdm progress bar already initialized

        # set some attributes
        self.pbar = pbar
        self._lock = threading.Lock()  # instantiate lock

    def __call__(self,
                 bytes_amount):  # amount of bytes received

        # acquire lock (for thread safety)
        with self._lock:
            # update tqdm progress bar with the bytes amount
            self.pbar.update(bytes_amount)


class BucketFileDownloader(object):
    """class used to download bucket files from an s3 bucket"""

    def __init__(self,
                 destination_dir,  # path to the destination folder where to save the element to
                 bucket_name):  # name of the s3 bucket where to find the element to download

        # set some attributes
        self._destination_dir = destination_dir
        self._bucketName = bucket_name

        # open boto3 client connection to the s3 bucket in anonymous mode
        self._s3client = boto3.client('s3',
                                      config=Config(signature_version=UNSIGNED))

    def __call__(self,
                 object_name):  # name (relative path wrt the s3 bucket) of the object to download

        # generate destination path where to save the element to
        dest_path = os.path.join(self._destination_dir, object_name)

        # create parent directory path if it does not exist (it succeeds even if the directory already exists)
        os.makedirs(Path(dest_path).parent.absolute(), exist_ok=True)

        logger.info("Now downloading {} from s3 bucket..".format(object_name))

        # retrieve metadata from the s3 object without returning the object itself
        response = self._s3client.head_object(Bucket=self._bucketName,
                                              Key=object_name)

        # extract total object size info from the response header
        size = response['ContentLength']

        # instantiate tqdm progress bar
        with tqdm.tqdm(total=size) as pbar:
            # download object file using boto3 'download_file' method
            # while passing it the ProgressPercentage as callback function
            # -> its call method will be called intermittently passing it the amount of bytes received
            self._s3client.download_file(self._bucketName,
                                         object_name,
                                         dest_path,
                                         Callback=ProgressPercentage(pbar))


@baker.command
def sorel20m_download(destination_dir):  # path to the destination folder where to save the element to
    """
    Download SOREL20M dataset elements from the s3 socket and save them in the specified destination directory.
    :param destination_dir: Path to the destination folder where to save the element to
    """

    # get absolute path if the one provided is relative
    if not os.path.isabs(destination_dir):
        destination_dir = os.path.abspath(destination_dir)

    os.makedirs(destination_dir, exist_ok=True)

    # start mlflow run
    with mlflow.start_run() as mlrun:
        # get dataset base absolute path
        dataset_base_path = os.path.dirname(os.path.join(destination_dir, needed_objects['meta']))

        # log dataset base path
        mlflow.log_text(dataset_base_path, artifact_file="dataset_base_path.txt")

        # check if all the needed files were already downloaded, if yes return
        if _check_files(destination_dir=destination_dir):
            logger.info("Found already downloaded dataset..")
            return

        # set SOREL20M bucket name
        bucket_name = "sorel-20m"
        # set SOREL20M dataset needed elements

        # instantiate bucket file downloader setting the destination dir and bucket name
        downloader = BucketFileDownloader(destination_dir, bucket_name)

        # select just the objects not already present
        objects_to_download = {key: obj for key, obj in needed_objects.items()
                               if not os.path.exists(os.path.join(destination_dir, obj))}

        # for all objects to download
        for i, (key, obj) in enumerate(objects_to_download.items()):
            if key == 'missing':
                # download shas_missing_ember_features.json
                url = 'https://raw.githubusercontent.com/sophos-ai/SOREL-20M/master/shas_missing_ember_features.json'
                r = requests.get(url, allow_redirects=True)

                # compute filename
                filename = os.path.join(destination_dir, obj)

                # save downloaded file
                with open(filename, 'wb') as f:
                    f.write(r.content)

            else:
                # download object (and save it in destination_dir)
                downloader(obj)

            logger.info("{}/{} done.".format(i + 1, len(objects_to_download)))


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()

