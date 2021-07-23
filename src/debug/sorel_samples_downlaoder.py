import os  # provides a portable way of using operating system dependent functionality

import baker  # easy, powerful access to Python functions from the command line
from logzero import logger  # robust and effective logging for Python

from utils.download_utils import BucketFileDownloader, check_files, needed_objects


@baker.command
def sorel20m_download(destination_dir):  # path to the destination folder where to save the element to
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
    dataset_base_path = os.path.dirname(os.path.join(destination_dir, needed_objects['binaries']))

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

        logger.info("{}/{} done.".format(i + 1, len(objects_to_download)))


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
