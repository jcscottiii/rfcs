import os
import yaml

from collections import defaultdict, OrderedDict
from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Set, Union, Optional, Any, TypeVar, Callable, Type, cast

WEB_FEATURE_FILENAME = "WEB_FEATURE.yml"

T = TypeVar("T")
EnumT = TypeVar("EnumT", bound=Enum)


def from_list(f: Callable[[Any], T], x: Any) -> List[T]:
    assert isinstance(x, list)
    return [f(y) for y in x]


def from_str(x: Any) -> str:
    assert isinstance(x, str)
    return x


def from_union(fs, x):
    for f in fs:
        try:
            return f(x)
        except:
            pass
    assert False


def from_none(x: Any) -> Any:
    assert x is None
    return x


def to_enum(c: Type[EnumT], x: Any) -> EnumT:
    assert isinstance(x, c)
    return x.value


def to_class(c: Type[T], x: Any) -> dict:
    assert isinstance(x, c)
    return cast(Any, x).to_dict()


class ApplyMode(Enum):
    """A specific file within the current directory
    
    Ignores features from previous parent directories.
    """
    IGNORE_PARENT = "IGNORE_PARENT"


class SpecialFileEnum(Enum):
    """All files recursively"""
    RECURSIVE = "**"


@dataclass
class FeatureEntry:
    files: Union[List[str], SpecialFileEnum]
    """The web feature key"""
    name: str

    @staticmethod
    def from_dict(obj: Any) -> 'FeatureEntry':
        assert isinstance(obj, dict)
        files = from_union([lambda x: from_list(from_str, x), SpecialFileEnum], obj.get("files"))
        name = from_str(obj.get("name"))
        return FeatureEntry(files, name)

    def to_dict(self) -> dict:
        result: dict = {}
        result["files"] = from_union([lambda x: from_list(from_str, x), lambda x: to_enum(SpecialFileEnum, x)], self.files)
        result["name"] = from_str(self.name)
        return result
    
    def does_feature_apply_recursively(self) -> bool:
        if isinstance(self.files, SpecialFileEnum) and self.files == SpecialFileEnum.RECURSIVE:
            return True
        return False


@dataclass
class WebFeatureYMLFile:
    """List of features"""
    features: List[FeatureEntry]
    apply_mode: Optional[ApplyMode] = None

    @staticmethod
    def from_dict(obj: Any) -> 'WebFeatureYMLFile':
        assert isinstance(obj, dict)
        features = from_list(FeatureEntry.from_dict, obj.get("features"))
        apply_mode = from_union([ApplyMode, from_none], obj.get("apply_mode"))
        return WebFeatureYMLFile(features, apply_mode)

    def to_dict(self) -> dict:
        result: dict = {}
        result["features"] = from_list(lambda x: to_class(FeatureEntry, x), self.features)
        if self.apply_mode is not None:
            result["apply_mode"] = from_union([lambda x: to_enum(ApplyMode, x), from_none], self.apply_mode)
        return result


def web_feature_yml_file_from_dict(s: Any) -> WebFeatureYMLFile:
    return WebFeatureYMLFile.from_dict(s)


def web_feature_yml_file_to_dict(x: WebFeatureYMLFile) -> Any:
    return to_class(WebFeatureYMLFile, x)

class FeatureResult:
    def __init__(self):
        self._feature_tests_map_ :OrderedDict[str, Set[str]]  = OrderedDict()
    def add(self, feature: str, test_files: List[str]):
        if self._feature_tests_map_.get(feature) == None:
            self._feature_tests_map_[feature] = set()
        self._feature_tests_map_[feature].update(test_files)
    def __repr__(self) -> str:
        return f"FeatureResult(_feature_tests_map_: {self._feature_tests_map_})"

FEATURE_RESULT = FeatureResult()


def parse_web_feature_yml(file_path: str) -> Optional[WebFeatureYMLFile]:
    """Parses a WEB_FEATURE.yml file into a WebFeatureYMLFile class.

    Args:
        file_path: The path to the WEB_FEATURE.yml file.

    Returns:
        - A WebFeatureYMLFile class containing the data from the WEB_FEATURE.yml file.
        - None if no file found
    """
    if not os.path.isfile(file_path):
        return None

    with open(file_path, "r") as f:
        data = yaml.load(f, Loader=yaml.FullLoader)

    # Validate the data format.

    if not isinstance(data, dict):
        raise ValueError("The WEB_FEATURE.yml file must be a YAML dictionary.")

    return web_feature_yml_file_from_dict(data)


def find_all_other_files_in_dir(dir: str) -> List[str]:
    return [os.path.join(dir,f) for f in os.listdir(dir)
        if WEB_FEATURE_FILENAME not in f and os.path.isfile(os.path.join(dir,f))]

VISITED_ROOTS = set()
def build_feature_to_test_map(dir_path: str, prev_inherited_features: List[FeatureEntry]=[]):
    for root, dirs, _ in os.walk(dir_path):
        if root in VISITED_ROOTS:
            continue
        VISITED_ROOTS.add(root)
        inherited_features = prev_inherited_features.copy()
        # Check if the current directory has a WEB_FEATURE_FILENAME
        current_files = find_all_other_files_in_dir(root)

        web_feature_file = parse_web_feature_yml(os.path.join(root, WEB_FEATURE_FILENAME))
        if web_feature_file:
            # print(os.path.join(root, WEB_FEATURE_FILENAME))
            if web_feature_file.apply_mode == ApplyMode.IGNORE_PARENT:
                inherited_features.clear()
            else:
                for inherited_feature in prev_inherited_features:
                    FEATURE_RESULT.add(inherited_feature.name, current_files)
            for feature in web_feature_file.features:
                if feature.does_feature_apply_recursively():
                    inherited_features.append(feature)
                    FEATURE_RESULT.add(feature.name, current_files)
                # If the feature does not apply recursively, look at the individual files and them.
                # TODO check if the list is empty.
                else:
                    filtered_files: List[str] = []
                    for test_file in feature.files:
                        complete_file_path = os.path.join(root, test_file)
                        # TODO ensure that the complete file path actually does not go to a parent directory
                        if os.path.isfile(complete_file_path):
                            filtered_files.append(test_file)
                        else:
                            # TODO handle missing file
                            pass
                    FEATURE_RESULT.add(feature.name, filtered_files)
        else:
            # No WEB_FEATURE.yml in this directory. Simply add the current features to the inherited features
            for inherited_feature in prev_inherited_features:
                FEATURE_RESULT.add(inherited_feature.name, current_files)

        for dir in dirs:
            build_feature_to_test_map(os.path.join(root, dir), inherited_features)

if __name__ == "__main__":
    wpt_root = "testdata"
    build_feature_to_test_map(wpt_root)
    print(repr(FEATURE_RESULT))