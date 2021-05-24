import os  # provides a portable way of using operating system dependent functionality

# needed fresh dataset objects
needed_objects = {"sig_to_label": "sig_to_label.json",
                  "X": "X_fresh.dat",
                  "y": "y_fresh.dat",
                  "S": "S_fresh.dat"}


def check_files(destination_dir):  # path to the destination folder where to save the elements to
    """ Check if the fresh dataset needed files were already created.

    Args:
        destination_dir: Path to the destination folder where to save the elements to
    Returns:
        True if there are all objects are present, False otherwise.
    """

    # select just the objects not already present from the needed objects
    absent_objects = {key: obj for key, obj in needed_objects.items()
                      if not os.path.exists(os.path.join(destination_dir, obj))}

    # if there are no objects to download return true
    return len(absent_objects) == 0
