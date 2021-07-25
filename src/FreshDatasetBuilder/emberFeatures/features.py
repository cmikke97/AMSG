""" Extracts some basic features from PE files. Many of the features
implemented have been used in previously published works. For more information,
check out the following resources:
* Schultz, et al., 2001: http://128.59.14.66/sites/default/files/binaryeval-ieeesp01.pdf
* Kolter and Maloof, 2006: http://www.jmlr.org/papers/volume7/kolter06a/kolter06a.pdf
* Shafiq et al., 2009: https://www.researchgate.net/profile/Fauzan_Mirza/publication/242084613_A_Framework_for_Efficient_Mining_of_Structural_Information_to_Detect_Zero-Day_Malicious_Portable_Executables/links/0c96052e191668c3d5000000.pdf
* Raman, 2012: http://2012.infosecsouthwest.com/files/speaker_materials/ISSW2012_Selecting_Features_to_Classify_Malware.pdf
* Saxe and Berlin, 2015: https://arxiv.org/pdf/1508.03096.pdf
It may be useful to do feature selection to reduce this set of features to a meaningful set
for your modeling problem.
"""

import hashlib  # common interface to many different secure hash and message digest algorithms
import re  # provides regular expression matching operations

import lief  # cross platform library which able to parse, modify and abstract ELF, PE and MachO formats
import numpy as np  # The fundamental package for scientific computing with Python
from sklearn.feature_extraction import FeatureHasher  # Implements feature hashing, aka the hashing trick
from logzero import logger

# get lief version
LIEF_MAJOR, LIEF_MINOR, _ = lief.__version__.split('.')
lief.logging.disable()

# check installed lief version capabilities
LIEF_EXPORT_OBJECT = int(LIEF_MAJOR) > 0 or (int(LIEF_MAJOR) == 0 and int(LIEF_MINOR) >= 10)
LIEF_HAS_SIGNATURE = int(LIEF_MAJOR) > 0 or (int(LIEF_MAJOR) == 0 and int(LIEF_MINOR) >= 11)


class FeatureType(object):
    """ Base class from which each feature type may inherit. """

    name = ''  # feature name
    dim = 0  # feature dimension

    def __repr__(self):  # get feature description (name + dim)
        """ Get unambiguous object representation in string format.

        Returns:
             Unambiguous object representation in string format.
        """

        return '{}({})'.format(self.name, self.dim)  # return formatted string

    def raw_features(self,
                     bytez,  # PE file binary data
                     lief_binary):  # lief parsing of PE file binaries
        """ Generate a JSON-able representation of the file (raw features).

        Args:
            bytez: PE file binary data
            lief_binary: Lief parsing of PE file binaries
        """

        raise NotImplementedError  # will be overridden by child classes

    def process_raw_features(self,
                             raw_obj):  # dictionary of raw features
        """ Generate a feature vector from the raw features.

        Args:
            raw_obj: Dictionary of raw features
        """

        raise NotImplementedError  # will be overridden by child classes

    def feature_vector(self,
                       bytez,  # PE file binary data
                       lief_binary):  # lief parsing of PE file binaries
        """ Directly calculate the feature vector from the sample itself. This should only be implemented differently
        if there are significant speedups to be gained from combining the two functions.

        Args:
            bytez: PE file binary data
            lief_binary: Lief parsing of PE file binaries
        Returns:
            Feature vector.
        """

        # get raw features from the sample; then generate feature vector
        return self.process_raw_features(self.raw_features(bytez, lief_binary))


class ByteHistogram(FeatureType):
    """ Byte histogram (count + non-normalized) over the entire binary file. """

    name = 'histogram'  # feature name
    dim = 256  # feature dimension

    def __init__(self):
        """ Initialize ByteHistogram class. """

        super(FeatureType, self).__init__()

    def raw_features(self,
                     bytez,  # PE file binary data
                     lief_binary):  # lief parsing of PE file binaries

        # interpret PE file binary data as a 1-dimensional array of (8-bit) unsigned integers,
        # then count the number of occurrences of each value in the array
        # (setting minimum number of bins for the output array to 256 to have always the same output size)
        # -> Each bin will give the number of occurrences of its index value in the original ndarray
        counts = np.bincount(np.frombuffer(bytez, dtype=np.uint8), minlength=256)

        # convert the numpy ndarray to a python list and return it
        return counts.tolist()

    def process_raw_features(self,
                             raw_obj):  # byte histogram raw features

        # create counts ndarray from the raw byte histogram interpreting the values as floats
        counts = np.array(raw_obj, dtype=np.float32)

        # sum all counts together
        counts_sum = counts.sum()

        # normalize counts dividing them by the total sum
        normalized = counts / counts_sum

        # return normalized histogram
        return normalized


class ByteEntropyHistogram(FeatureType):
    """ 2d byte/entropy histogram based loosely on (Saxe and Berlin, 2015).
    This roughly approximates the joint probability of byte value and local entropy.
    See Section 2.1.1 in https://arxiv.org/pdf/1508.03096.pdf for more info.
    """

    name = 'byteentropy'
    dim = 256

    def __init__(self,
                 step=1024,  # step size
                 window=2048):  # window size
        """ Initialize ByteEntropyHistogram class. """

        super(FeatureType, self).__init__()

        # set attributes
        self.window = window
        self.step = step

    def _entropy_bin_counts(self,
                            block):  # ndarray containing a piece (block) of the PE file binary data
        """ Get bin frequencies (counts) and entropy bin index (Hbin).

        Args:
            block: Ndarray containing a piece (block) of the PE file binary data
        Returns:
            Entropy bin index (Hbin) and bin frequencies (counts).
        """

        # calculate bin frequency:
        # shift block bytes to the right by 4 positions (dividing them by 16),
        # then count the number of occurrences of each value in the array
        # (setting minimum number of bins for the output array to 16)
        # in order to have a coarse histogram, with 16 bytes per bin
        c = np.bincount(block >> 4, minlength=16)  # 16-bin histogram

        # calculate bin probability:
        # get a copy of "c" ndarray, casting its values to float and then dividing them by the window size
        p = c.astype(np.float32) / self.window

        # get non-zero bins indexes (where(c) -> where c is not zero)
        wh = np.where(c)[0]

        # calculate entropy:
        # get p values where c is not zero, multiply them with the -log2 of themselves,
        # sum the results and then multiply by 2
        # (x2 because we reduced information by half: 256 bins (8 bits) to 16 bins (4 bits))
        H = np.sum(-p[wh] * np.log2(p[wh])) * 2

        # get the bin index where to store histogram "c", we have up to 16 bins (max entropy is 8 bits)
        Hbin = int(H * 2)
        if Hbin == 16:  # handle entropy = 8.0 bits
            Hbin = 15

        # return bin index "Hbin" and histogram "c"
        return Hbin, c

    def raw_features(self,
                     bytez,  # PE file binary data
                     lief_binary):  # lief parsing of PE file binaries

        # initialize output as a 2d grid of 16x16 zeros (ints)
        output = np.zeros((16, 16), dtype=np.int)

        # interpret PE file binary data as a 1-dimensional array of (8-bit) unsigned integers
        a = np.frombuffer(bytez, dtype=np.uint8)

        if a.shape[0] < self.window:  # if the size of ndarray "a" is less than the window size

            # get 16-bin histogram "c" and bin index "Hbin" from ndarray "a"
            Hbin, c = self._entropy_bin_counts(a)

            # save histogram in output adding counts at the specified bin index
            output[Hbin, :] += c

        else:
            # strided trick from here: http://www.rigtorp.se/2011/01/01/rolling-statistics-numpy.html

            # get shape for stride_tricks.as_strided
            shape = a.shape[:-1] + (a.shape[-1] - self.window + 1, self.window)

            # get strides stride_tricks.as_strided: bytes to step in each dimension when traversing the ndarray
            strides = a.strides + (a.strides[-1],)

            # create a view into the "a" ndarray with the given shape and strides, getting one row every "step" steps
            blocks = np.lib.stride_tricks.as_strided(a, shape=shape, strides=strides)[::self.step, :]

            # from the blocks, compute histogram
            for block in blocks:
                # get 16-bin histogram "c" and bin index "Hbin" from ndarray block
                Hbin, c = self._entropy_bin_counts(block)

                # save histogram in output adding counts at the specified bin index
                output[Hbin, :] += c

        # get a copy of the output ndarray collapsed into one dimension,
        # then convert the numpy ndarray to a python list and return it
        return output.flatten().tolist()

    def process_raw_features(self,
                             raw_obj):  # byte entropy histogram raw features

        # create counts ndarray from the raw byte entropy histogram interpreting the values as floats
        counts = np.array(raw_obj, dtype=np.float32)

        # sum all counts together
        counts_sum = counts.sum()

        # normalize counts dividing them by the total sum
        normalized = counts / counts_sum

        # return normalized histogram
        return normalized


class SectionInfo(FeatureType):
    """ Information about section names, sizes and entropy.
    Uses hashing trick to summarize all this section info into a feature vector.
    """

    name = 'section'
    dim = 5 + 50 + 50 + 50 + 50 + 50

    def __init__(self):
        """ Initialize SectionInfo class. """

        super(FeatureType, self).__init__()

    @staticmethod
    def _properties(s):  # lief binary section
        """ Get section characteristics list.

        Args:
            s: Lief binary section
        Returns:
            Section characteristics list.
        """

        # get section characteristics list, throwing away any string preceding the last "."
        return [str(c).split('.')[-1] for c in s.characteristics_lists]

    def raw_features(self,
                     bytez,  # PE file binary data
                     lief_binary):  # lief parsing of PE file binaries

        # if the leaf parsing is None just return empty section info feature
        if lief_binary is None:
            return {"entry": "", "sections": []}

        # properties of entry point, or if invalid, the first executable section
        try:
            # get entry section name
            entry_section = lief_binary.section_from_offset(lief_binary.entrypoint).name
        except lief.not_found:
            # bad entry point, let's find the first executable section
            entry_section = ""
            for s in lief_binary.sections:  # for all the binary sections
                # if the current section is executable (MEM_EXECUTE is in the section characteristics)
                if lief.PE.SECTION_CHARACTERISTICS.MEM_EXECUTE in s.characteristics_lists:
                    # set entry section name
                    entry_section = s.name
                    break

        # set entry name in raw object dictionary
        raw_obj = {"entry": entry_section, "sections": [{
            'name': s.name,  # section name
            'size': s.size,  # section size
            'entropy': s.entropy,  # section entropy
            'vsize': s.virtual_size,  # section virtual size
            'props': self._properties(s)  # section properties
        } for s in lief_binary.sections]}

        # for every section add its properties to "sections" vector in raw object dictionary

        # return raw object dictionary
        return raw_obj

    def process_raw_features(self,
                             raw_obj):  # section info raw features

        # get sections (vector) from raw object dictionary
        sections = raw_obj['sections']

        # set general info
        general = [
            len(sections),  # total number of sections
            # number of sections with nonzero size
            sum(1 for s in sections if s['size'] == 0),
            # number of sections with an empty name
            sum(1 for s in sections if s['name'] == ""),
            # number of RX sections
            sum(1 for s in sections if 'MEM_READ' in s['props'] and 'MEM_EXECUTE' in s['props']),
            # number of W sections
            sum(1 for s in sections if 'MEM_WRITE' in s['props'])
        ]

        # gross characteristics of each section

        # get sections' names and sizes
        section_sizes = [(s['name'], s['size']) for s in sections]
        # use Feature Hasher to do the hashing trick on section_sizes
        section_sizes_hashed = FeatureHasher(50, input_type="pair").transform([section_sizes]).toarray()[0]
        # get sections' entropies
        section_entropy = [(s['name'], s['entropy']) for s in sections]
        # do the hashing trick on section_entropy
        section_entropy_hashed = FeatureHasher(50, input_type="pair").transform([section_entropy]).toarray()[0]
        # get sections' virtual sizes
        section_vsize = [(s['name'], s['vsize']) for s in sections]
        # do the hashing trick on section_vsize
        section_vsize_hashed = FeatureHasher(50, input_type="pair").transform([section_vsize]).toarray()[0]
        # do the hashing trick on sections' entry names
        entry_name_hashed = FeatureHasher(50, input_type="string").transform([raw_obj['entry']]).toarray()[0]
        # get entry sections' characteristics (properties)
        characteristics = [p for s in sections for p in s['props'] if s['name'] == raw_obj['entry']]
        # do the hashing trick on entry sections' characteristics
        characteristics_hashed = FeatureHasher(50, input_type="string").transform([characteristics]).toarray()[0]

        # concatenate characteristics ndarrays in sequence horizontally,
        # then copy of the array casting its values to float; then return it
        return np.hstack([
            general, section_sizes_hashed, section_entropy_hashed, section_vsize_hashed, entry_name_hashed,
            characteristics_hashed
        ]).astype(np.float32)


class ImportsInfo(FeatureType):
    """ Information about imported libraries and functions from the import address table.
    Note that the total number of imported functions is contained in GeneralFileInfo.
    """

    name = 'imports'
    dim = 1280

    def __init__(self):
        """ Initialize ImportsInfo class. """

        super(FeatureType, self).__init__()

    def raw_features(self,
                     bytez,  # PE file binary data
                     lief_binary):  # lief parsing of PE file binaries

        # initialize imports as an empty dictionary
        imports = {}
        if lief_binary is None:  # if lief binary object is None then return the empty imports raw feature
            return imports

        # for each imported library
        for lib in lief_binary.imports:
            # if the library is not yet in the imports dictionary
            if lib.name not in imports:
                imports[lib.name] = []  # libraries can be duplicated in listing, extend instead of overwrite

            # Clipping assumes there are diminishing returns on the discriminatory power of imported functions
            # beyond the first 10000 characters, and this will help limit the dataset size
            for entry in lib.entries:  # for each imported entry (function) in the library
                if entry.is_ordinal:  # if ordinal is used
                    imports[lib.name].append("ordinal" + str(entry.ordinal))  # append entry ordinal value
                else:
                    imports[lib.name].append(entry.name[:10000])  # append entry name truncated to the first 10000 chars

        # return imports dictionary
        return imports

    def process_raw_features(self,
                             raw_obj):  # imports info raw features

        # get unique libraries
        libraries = list(set([lib.lower() for lib in raw_obj.keys()]))
        # do the hashing trick on libraries names
        libraries_hashed = FeatureHasher(256, input_type="string").transform([libraries]).toarray()[0]

        # generate a string like "kernel32.dll:CreateFileMappingA" for each imported function
        imports = [lib.lower() + ':' + e for lib, elist in raw_obj.items() for e in elist]
        # do the hashing trick on imports
        imports_hashed = FeatureHasher(1024, input_type="string").transform([imports]).toarray()[0]

        # return two separate elements: libraries (alone) and fully-qualified names of imported functions
        # stacked together in a single, one dimensional, array with values of type float
        return np.hstack([libraries_hashed, imports_hashed]).astype(np.float32)


class ExportsInfo(FeatureType):
    """ Information about exported functions.
    Note that the total number of exported functions is contained in GeneralFileInfo.
    """

    name = 'exports'
    dim = 128

    def __init__(self):
        """ Initialize ExportsInfo class. """

        super(FeatureType, self).__init__()

    def raw_features(self,
                     bytez,  # PE file binary data
                     lief_binary):  # lief parsing of PE file binaries

        # if lief binary object is None return an empty vector
        if lief_binary is None:
            return []

        # Clipping assumes there are diminishing returns on the discriminatory power of exports beyond
        # the first 10000 characters, and this will help limit the dataset size
        if LIEF_EXPORT_OBJECT:
            # export is an object with .name attribute (0.10.0 and later) -> get export functions' names (clipped)
            clipped_exports = [export.name[:10000] for export in lief_binary.exported_functions]
        else:
            # export is a string (LIEF 0.9.0 and earlier)
            clipped_exports = [export[:10000] for export in lief_binary.exported_functions]

        # return exports raw feature
        return clipped_exports

    def process_raw_features(self,
                             raw_obj):  # exports info raw features

        # do the hashing trick on exported functions raw feature
        exports_hashed = FeatureHasher(128, input_type="string").transform([raw_obj]).toarray()[0]

        # return exported functions feature vector
        return exports_hashed.astype(np.float32)


class GeneralFileInfo(FeatureType):
    """ General information about the file. """

    name = 'general'
    dim = 10

    def __init__(self):
        """ Initialize GeneralFileInfo class. """

        super(FeatureType, self).__init__()

    def raw_features(self,
                     bytez,  # PE file binary data
                     lief_binary):  # lief parsing of PE file binaries

        # if lief binary object is None return a general file info dictionary with default (zero) values
        if lief_binary is None:
            return {
                'size': len(bytez),  # the only property we can compute
                'vsize': 0,
                'has_debug': 0,
                'exports': 0,
                'imports': 0,
                'has_relocations': 0,
                'has_resources': 0,
                'has_signature': 0,
                'has_tls': 0,
                'symbols': 0
            }

        # return general file info dictionary
        return {
            'size': len(bytez),  # get PE file binaries length
            'vsize': lief_binary.virtual_size,  # get virtual size
            'has_debug': int(lief_binary.has_debug),  # get whether the current binary has a Debug object
            'exports': len(lief_binary.exported_functions),  # get number of exported functions
            'imports': len(lief_binary.imported_functions),  # get number of imported functions
            'has_relocations': int(lief_binary.has_relocations),  # get whether the current binary uses Relocation
            'has_resources': int(lief_binary.has_resources),  # get whether the current binary has a Resources object
            # get whether the binary has signatures
            'has_signature': int(lief_binary.has_signatures) if LIEF_HAS_SIGNATURE else int(lief_binary.has_signature),
            'has_tls': int(lief_binary.has_tls),  # get whether the current binary has a TLS object
            'symbols': len(lief_binary.symbols),  # get number of binary's symbols
        }

    def process_raw_features(self,
                             raw_obj):  # general file info raw features

        # return one single ndarray of float values, concatenating together the raw general file info features
        return np.asarray([
            raw_obj['size'], raw_obj['vsize'], raw_obj['has_debug'], raw_obj['exports'], raw_obj['imports'],
            raw_obj['has_relocations'], raw_obj['has_resources'], raw_obj['has_signature'], raw_obj['has_tls'],
            raw_obj['symbols']
        ], dtype=np.float32)


class HeaderFileInfo(FeatureType):
    """ Machine, architecture, OS, linker and other information extracted from header. """

    name = 'header'
    dim = 62

    def __init__(self):
        """ Initialize HeaderFileInfo class. """

        super(FeatureType, self).__init__()

    def raw_features(self,
                     bytez,  # PE file binary data
                     lief_binary):  # lief parsing of PE file binaries

        # instantiate header file info raw object dictionary
        raw_obj = {'coff': {'timestamp': 0, 'machine': "", 'characteristics': []},
                   'optional': {
                       'subsystem': "",
                       'dll_characteristics': [],
                       'magic': "",
                       'major_image_version': 0,
                       'minor_image_version': 0,
                       'major_linker_version': 0,
                       'minor_linker_version': 0,
                       'major_operating_system_version': 0,
                       'minor_operating_system_version': 0,
                       'major_subsystem_version': 0,
                       'minor_subsystem_version': 0,
                       'sizeof_code': 0,
                       'sizeof_headers': 0,
                       'sizeof_heap_commit': 0
                   }}

        # initialize header file info raw object dictionary with default values

        # if lief binary object is None return default raw object
        if lief_binary is None:
            return raw_obj

        # get coff header timestamp (when the file was created)
        raw_obj['coff']['timestamp'] = lief_binary.header.time_date_stamps
        # get the coff header machine (throwing away any string before the last ".")
        raw_obj['coff']['machine'] = str(lief_binary.header.machine).split('.')[-1]
        # get coff header characteristics (throwing away any string before the last ".")
        raw_obj['coff']['characteristics'] = [str(c).split('.')[-1] for c in lief_binary.header.characteristics_list]
        # get the optional header subsystem required to run this image (throwing away any string before the last ".")
        raw_obj['optional']['subsystem'] = str(lief_binary.optional_header.subsystem).split('.')[-1]
        # get the optional header dll characteristics (throwing away any string before the last ".")
        raw_obj['optional']['dll_characteristics'] = [
            str(c).split('.')[-1] for c in lief_binary.optional_header.dll_characteristics_lists
        ]
        # get the optional header magic value (throwing away any string before the last ".")
        raw_obj['optional']['magic'] = str(lief_binary.optional_header.magic).split('.')[-1]
        # get the optional header major image version
        raw_obj['optional']['major_image_version'] = lief_binary.optional_header.major_image_version
        # get the optional header minor image version
        raw_obj['optional']['minor_image_version'] = lief_binary.optional_header.minor_image_version
        # get the optional header major linker version
        raw_obj['optional']['major_linker_version'] = lief_binary.optional_header.major_linker_version
        # get the optional header minor linker version
        raw_obj['optional']['minor_linker_version'] = lief_binary.optional_header.minor_linker_version
        # get the optional header major operating system version required
        raw_obj['optional'][
            'major_operating_system_version'] = lief_binary.optional_header.major_operating_system_version
        # get the optional header minor operating system version required
        raw_obj['optional'][
            'minor_operating_system_version'] = lief_binary.optional_header.minor_operating_system_version
        # get the optional header majosr subsystem version
        raw_obj['optional']['major_subsystem_version'] = lief_binary.optional_header.major_subsystem_version
        # get the optional header mino subsystem version
        raw_obj['optional']['minor_subsystem_version'] = lief_binary.optional_header.minor_subsystem_version
        # get the optional header size of the code (text) section (or sum of code sizes if there are multiple sections)
        raw_obj['optional']['sizeof_code'] = lief_binary.optional_header.sizeof_code
        # get the optional header combined size of an MS-DOS stub, PE header, and section headers
        raw_obj['optional']['sizeof_headers'] = lief_binary.optional_header.sizeof_headers
        # get the optional header size of the local heap space to commit
        raw_obj['optional']['sizeof_heap_commit'] = lief_binary.optional_header.sizeof_heap_commit

        # return raw object dictionary
        return raw_obj

    def process_raw_features(self,
                             raw_obj):  # header file info raw features

        # return one single 1-D ndarray of float values obtained concatenating along one dimension the raw features,
        # some of which are transformed through the hashing trick
        return np.hstack([
            raw_obj['coff']['timestamp'],
            FeatureHasher(10, input_type="string").transform([[raw_obj['coff']['machine']]]).toarray()[0],
            FeatureHasher(10, input_type="string").transform([raw_obj['coff']['characteristics']]).toarray()[0],
            FeatureHasher(10, input_type="string").transform([[raw_obj['optional']['subsystem']]]).toarray()[0],
            FeatureHasher(10, input_type="string").transform([raw_obj['optional']['dll_characteristics']]).toarray()[0],
            FeatureHasher(10, input_type="string").transform([[raw_obj['optional']['magic']]]).toarray()[0],
            raw_obj['optional']['major_image_version'],
            raw_obj['optional']['minor_image_version'],
            raw_obj['optional']['major_linker_version'],
            raw_obj['optional']['minor_linker_version'],
            raw_obj['optional']['major_operating_system_version'],
            raw_obj['optional']['minor_operating_system_version'],
            raw_obj['optional']['major_subsystem_version'],
            raw_obj['optional']['minor_subsystem_version'],
            raw_obj['optional']['sizeof_code'],
            raw_obj['optional']['sizeof_headers'],
            raw_obj['optional']['sizeof_heap_commit'],
        ]).astype(np.float32)


class StringExtractor(FeatureType):
    """ Extracts strings from raw byte stream. """

    name = 'strings'
    dim = 1 + 1 + 1 + 96 + 1 + 1 + 1 + 1 + 1

    def __init__(self):
        """ Initialize StringExtractor class. """

        super(FeatureType, self).__init__()
        # compile a bunch of regular expression patterns into regular expression objects to be later used for matching

        # all consecutive runs of 0x20 - 0x7f that are 5+ characters
        self._allstrings = re.compile(b'[\x20-\x7f]{5,}')
        # occurances of the string 'C:\'.  Not actually extracting the path
        self._paths = re.compile(b'c:\\\\', re.IGNORECASE)
        # occurances of http:// or https://.  Not actually extracting the URLs
        self._urls = re.compile(b'https?://', re.IGNORECASE)
        # occurances of the string prefix HKEY_.  No actually extracting registry names
        self._registry = re.compile(b'HKEY_')
        # crude evidence of an MZ header (dropper?) somewhere in the byte stream
        self._mz = re.compile(b'MZ')

    def raw_features(self,
                     bytez,  # PE file binary data
                     lief_binary):  # lief parsing of PE file binaries

        # find all occurrencies of _allstrings in the PE file binary data
        allstrings = self._allstrings.findall(bytez)
        if allstrings:  # if at least one string has been matched
            # statistics about strings:

            # get the length of each string
            string_lengths = [len(s) for s in allstrings]
            # compute average string length
            avlength = sum(string_lengths) / len(string_lengths)
            # map printable characters 0x20 - 0x7f to an int array consisting of 0-95, inclusive
            as_shifted_string = [b - ord(b'\x20') for b in b''.join(allstrings)]
            # compute histogram count for the 96 letters (distribution of characters in printable strings)
            c = np.bincount(as_shifted_string, minlength=96)
            # sum counts
            csum = c.sum()
            # compute character probabilities (as floats)
            p = c.astype(np.float32) / csum
            # get non-zero bin indexes
            wh = np.where(c)[0]
            # calculate entropy
            H = np.sum(-p[wh] * np.log2(p[wh]))
        else:  # if no strings were matched set to zero (default value) some variables
            avlength = 0
            c = np.zeros((96,), dtype=np.float32)  # histogram of all zeros
            H = 0
            csum = 0

        # return raw object dictionary with the computed information
        return {
            'numstrings': len(allstrings),  # total number of strings found in the PE file
            'avlength': avlength,  # average string length
            'printabledist': c.tolist(),  # non-normalized printable characters frequency histogram
            'printables': int(csum),  # total number of printable characters found
            'entropy': float(H),  # entropy
            'paths': len(self._paths.findall(bytez)),  # number of found paths
            'urls': len(self._urls.findall(bytez)),  # number of found urls
            'registry': len(self._registry.findall(bytez)),  # number of found registry names
            'MZ': len(self._mz.findall(bytez))  # number of found MZ headers
        }

    def process_raw_features(self,
                             raw_obj):  # string extractor raw features

        # set histogram divisor as csum (printables) if it was > 0, to 1.0 otherwise
        hist_divisor = float(raw_obj['printables']) if raw_obj['printables'] > 0 else 1.0

        # return one single 1-D ndarray of float values obtained concatenating together the raw features
        # (normalizing the printable characters histogram)
        return np.hstack([
            raw_obj['numstrings'],
            raw_obj['avlength'],
            raw_obj['printables'],
            np.asarray(raw_obj['printabledist']) / hist_divisor,  # divide distribution by the previously set divisor
            raw_obj['entropy'],
            raw_obj['paths'],
            raw_obj['urls'],
            raw_obj['registry'],
            raw_obj['MZ']
        ]).astype(np.float32)


class DataDirectories(FeatureType):
    """ Extracts size and virtual address of the first 15 data directories. """

    name = 'datadirectories'
    dim = 15 * 2

    def __init__(self):
        """ Initialize DataDirectories class. """

        super(FeatureType, self).__init__()

        # define data directory names order
        self._name_order = [
            "EXPORT_TABLE", "IMPORT_TABLE", "RESOURCE_TABLE", "EXCEPTION_TABLE", "CERTIFICATE_TABLE",
            "BASE_RELOCATION_TABLE", "DEBUG", "ARCHITECTURE", "GLOBAL_PTR", "TLS_TABLE", "LOAD_CONFIG_TABLE",
            "BOUND_IMPORT", "IAT", "DELAY_IMPORT_DESCRIPTOR", "CLR_RUNTIME_HEADER"
        ]

    def raw_features(self,
                     bytez,  # PE file binary data
                     lief_binary):  # lief parsing of PE file binaries

        # instantiate output vector
        output = []

        # if lief binary object is None return empty output raw object
        if lief_binary is None:
            return output

        # for each data directory
        for data_directory in lief_binary.data_directories:
            # append info to output vector
            output.append({
                # set data directory type name (removing the "DATA_DIRECTORY." prefix)
                "name": str(data_directory.type).replace("DATA_DIRECTORY.", ""),
                "size": data_directory.size,  # set data directory size
                "virtual_address": data_directory.rva  # set data directory virtual address
            })

        # return output raw feature vector
        return output

    def process_raw_features(self,
                             raw_obj):  # data dictionaries raw features

        # initialize features vector with size equal to 2 times the number of data directory types
        # with all zeros (as floats)
        features = np.zeros(2 * len(self._name_order), dtype=np.float32)

        # iterate for a number of times equal to the number of data directory types
        for i in range(len(self._name_order)):
            if i < len(raw_obj):
                # set data directory size to the feature vector at an even position
                features[2 * i] = raw_obj[i]["size"]
                # set data directory virtual address to the feature vector at an odd position
                features[2 * i + 1] = raw_obj[i]["virtual_address"]

        # return data directory feature vector
        return features


class PEFeatureExtractor(object):
    """ Extract useful features from a PE file, and return as a vector of fixed size. """

    def __init__(self,
                 feature_version=2,  # EMBER feature version
                 print_feature_warning=True):  # whether to print warnings or not
        """ Initialize PEFeatureExtractor class.

        Args:
            feature_version: EMBER feature version
            print_feature_warning: Whether to print warnings or not
        """

        # define features to extract from PE file binaries
        self.features = [
            ByteHistogram(),
            ByteEntropyHistogram(),
            StringExtractor(),
            GeneralFileInfo(),
            HeaderFileInfo(),
            SectionInfo(),
            ImportsInfo(),
            ExportsInfo()
        ]

        # check EMBER feature version selected against current lief version
        if feature_version == 1:
            if not lief.__version__.startswith("0.8.3"):
                if print_feature_warning:
                    print("WARNING: EMBER feature version 1 were computed using lief version 0.8.3-18d5b75")
                    print("WARNING: lief version {} found instead. There may be slight inconsistencies"
                          .format(lief.__version__))
                    print("WARNING: in the feature calculations.")
        elif feature_version == 2:
            self.features.append(DataDirectories())  # append another type of feature specific to version 2
            if not lief.__version__.startswith("0.9.0"):
                if print_feature_warning:
                    print("WARNING: EMBER feature version 2 were computed using lief version 0.9.0-")
                    print("WARNING: lief version {} found instead. There may be slight inconsistencies"
                          .format(lief.__version__))
                    print("WARNING: in the feature calculations.")
        else:
            raise Exception(f"EMBER feature version must be 1 or 2. Not {feature_version}")

        # compute features total dimension
        self.dim = sum([fe.dim for fe in self.features])

    def raw_features(self,
                     bytez):  # PE file binary data

        # define all lief errors we want to intercept
        lief_errors = (lief.bad_format, lief.bad_file, lief.pe_error, lief.parser_error, lief.read_out_of_bound,
                       RuntimeError)
        try:
            lief_binary = lief.PE.parse(list(bytez))  # Parse the given PE file binaries and return a Binary object
        except lief_errors as e:  # if any of the previously defined lief errors is raised
            logger.warn("lief error: ", str(e))  # print the error
            return None
        except Exception:  # if any other exception (KeyboardInterrupt, SystemExit, ValueError) is raised:
            raise  # raise exception

        # calculate sha256 hash (hex) digest of the PE file binaries
        features = {"sha256": hashlib.sha256(bytez).hexdigest()}

        # compute all the other raw features and append them to the features dictionary
        features.update({fe.name: fe.raw_features(bytez, lief_binary) for fe in self.features})

        # return computed raw features for the current PE file binaries
        return features

    def process_raw_features(self,
                             raw_obj):  # dictionary of raw features

        # compute feature vector by processing the raw features in the raw features dictionary
        feature_vectors = [fe.process_raw_features(raw_obj[fe.name]) for fe in self.features]

        # concatenate feature vectors (horizontally) in a single numpy array,
        # and return a copy of the array casting its values to float32
        return np.hstack(feature_vectors).astype(np.float32)

    def feature_vector(self,
                       bytez):  # PE file data

        # get raw features from PE file data,
        # then generate feature vector from raw features
        return self.process_raw_features(self.raw_features(bytez))
