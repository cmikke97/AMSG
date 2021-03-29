import boto3  # Used to create, configure, and manage AWS services (s3 included)
from botocore import UNSIGNED # constant to use to connect to s3 bucket anonymously (botocore is the Low-level, data-driven core of boto 3) 
from botocore.client import Config  # Advanced configuration for Botocore clients (botocore is the Low-level, data-driven core of boto 3)
import baker  # Easy, powerful access to Python functions from the command line
import os # Provides a portable way of using operating system dependent functionality
import sys  # System-specific parameters and functions
import threading  #  Constructs higher-level threading interfaces on top of the lower level _thread module
from pathlib import Path  # offers classes representing filesystem paths with semantics appropriate for different operating systems
from tqdm import tqdm # Instantly makes loops show a smart progress meter

class ProgressPercentage(object):

    def __init__(self,
                 pbar): # tqdm progress bar already initialized

        # set some attributes
        self.pbar = pbar
        self._lock = threading.Lock() # instantiate lock

    def __call__(self,
                 bytes_amount): # amount of bytes received

        # acquire lock (for thread safety)
        with self._lock:
            # update tqdm progress bar with the bytes amount
            self.pbar.update(bytes_amount)


class BucketFileDownloader(object):

    def __init__(self,
                 destination_dir, # path to the destination folder where to save the element to
                 bucket_name):  # name of the s3 bucket where to find the element to download

        # set some attributes
        self._destination_dir = destination_dir
        self._bucketName = bucket_name

        # open boto3 client connection to the s3 bucket in anonymous mode
        self._s3client = boto3.client('s3', 
                                      config = Config(signature_version = UNSIGNED))


    def __call__(self,
                 object_name):  # name (relative path wrt the s3 bucket) of the object to download

        # generate destination path where to save the element to
        dest_path = self._destination_dir + object_name

        # create parent directory path if it does not exist (it succeeds even if the directory already exists)
        os.makedirs(Path(dest_path).parent.absolute(), exist_ok=True)

        # print info
        print("Now downloading {} from s3 bucket..".format(object_name))

        # retrieve metadata from the s3 object without returning the object itself
        response = self._s3client.head_object(Bucket = bucket_name,
                                              Key = object_name)
        
        # extract total object size info from the response header
        size = response['ContentLength']

        # instantiate tqdm progress bar
        with tqdm(total = size) as pbar:
            # download object file using boto3 'download_file' method
            # while passing it the ProgressPercentage as callback function
            # -> its call method will be called intermittently passing it the amount of bytes received
            self._s3client.download_file(self._bucketName,
                                         object_name,
                                         dest_path,
                                         Callback=ProgressPercentage(pbar))
        
        #print info
        print("{} downloaded succesfully.".format(object_name))


@baker.command
def SOREL20M_Download(destination_dir):	# path to the destination folder where to save the element to
		"""
    Download SOREL20M dataset elements from the s3 socket.
    
    :param destination_dir: Path to the destination folder where to save the element to
    """

    # set SOREL20M bucket name
    bucket_name = "sorel-20m"
    # set SOREL20M dataset elements to be downloaded
    objects_to_download = ["09-DEC-2020/processed-data/meta.db",
                           "09-DEC-2020/processed-data/ember_features/data.mdb",
                           "09-DEC-2020/processed-data/ember_features/lock.mdb"]

    # instantiate bucket file downloader setting the destination dir and bucket name
    downloader = BucketFileDownloader(destination_dir, bucket_name)

    # for all objects to download
    for i, obj in enumerate(objects_to_download):
        # download object (and save it in destination_dir)
        downloader(obj)
        # print info on std out
        print("{}/{} done.".format(i, len(objects_to_download)))

if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
