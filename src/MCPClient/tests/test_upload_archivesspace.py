"""Tests for the upload_archivesspace.py client script."""

import os
import sys
import uuid

import pytest

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.abspath(os.path.join(THIS_DIR, "../lib/clientScripts")))

import upload_archivesspace


def test_recursive_file_gen(tmpdir):
    mydir = tmpdir.mkdir("mydir")
    hello = mydir.join("hello.txt")
    hello.write("hello!")
    bye = mydir.mkdir("sub").join("bye.txt")
    bye.write("bye!")
    result = list(upload_archivesspace.recursive_file_gen(str(mydir)))
    assert sorted(result) == [str(hello), str(bye)]


def test_get_files_from_dip_finds_files(tmpdir):
    dip = tmpdir.mkdir("mydip")
    objects = dip.mkdir("objects")
    object1 = objects.join("object1.txt")
    object1.write("object 1")
    object2 = objects.mkdir("subdir").join("object2.txt")
    object2.write("object 2")
    # TODO:
    # - use os.path.join in the function and make trailing slash optional
    # - remove last two parameters, they're not used in the function
    result = upload_archivesspace.get_files_from_dip(str(dip) + "/", None, None)
    assert sorted(result) == [str(object1), str(object2)]


def test_get_files_from_dip_with_empty_dip_location(tmpdir, mocker):
    logger = mocker.patch("upload_archivesspace.logger")
    dip = tmpdir.mkdir("mydip")
    with pytest.raises(ValueError) as excinfo:
        upload_archivesspace.get_files_from_dip(str(dip) + "/", None, None)
    assert excinfo.value.message == "cannot find dip"
    logger.error.assert_called_once_with("no files in {}/objects/".format(str(dip)))


def test_get_pairs(mocker):
    dip_uuid = "somedipuuid"
    filter_mock = mocker.patch(
        "upload_archivesspace.ArchivesSpaceDIPObjectResourcePairing.objects.filter",
        return_value=[
            mocker.Mock(fileuuid="1", resourceid="myresource"),
            mocker.Mock(fileuuid="2", resourceid="myresource"),
        ],
    )
    result = upload_archivesspace.get_pairs(dip_uuid)
    assert result == {"1": "myresource", "2": "myresource"}
    filter_mock.assert_called_once_with(dipuuid=dip_uuid)


def test_delete_pairs(mocker):
    dip_uuid = "somedipuuid"
    queryset_mock = mocker.Mock()
    filter_mock = mocker.patch(
        "upload_archivesspace.ArchivesSpaceDIPObjectResourcePairing.objects.filter",
        return_value=queryset_mock,
    )
    upload_archivesspace.delete_pairs(dip_uuid)
    filter_mock.assert_called_once_with(dipuuid=dip_uuid)
    queryset_mock.delete.assert_called_once()


@pytest.mark.parametrize(
    "uri",
    ["http://some/uri/", "http://some/uri"],
    ids=["uri_with_trailing_slash", "uri_with_no_trailing_slash"],
)
def test_upload_to_archivespace_adds_trailing_slash_to_uri(db, mocker, uri):
    file_uuid = str(uuid.uuid4())
    client_mock = mocker.Mock()
    mocker.patch("upload_archivesspace.mets_file")
    mocker.patch(
        "upload_archivesspace.get_pairs", return_value={file_uuid: "myresource"}
    )
    files = ["file/{}-path".format(file_uuid)]
    # TODO: initialize restriction_apply = None/False before determining restrictions
    #       to avoid referenced before assignment error if restrictions is no in the
    #       expected values
    restrictions = "no"
    upload_archivesspace.upload_to_archivesspace(
        files, client_mock, "", "", "", "", uri, "", "", "", restrictions, "", ""
    )
    client_mock.add_digital_object.assert_called_once_with(
        **{
            "access_conditions": "",
            "format_name": None,
            "format_version": None,
            "identifier": file_uuid,
            "inherit_notes": "",
            "location_of_originals": "",
            "object_type": "",
            "parent_archival_object": "myresource",
            "restricted": False,
            "size": None,
            "title": "",
            # whole point of this test is to check this path is correct
            "uri": "http://some/uri/{}-path".format(file_uuid),
            "use_conditions": "",
            "use_statement": "",
            "xlink_actuate": "",
            "xlink_show": "",
        }
    )


@pytest.mark.parametrize(
    "params",
    [
        {"restrictions": "premis", "access_conditions": "", "use_conditions": ""},
        {
            "restrictions": "",
            "access_conditions": "somecondition",
            "use_conditions": "",
        },
        {
            "restrictions": "",
            "access_conditions": "",
            "use_conditions": "somecondition",
        },
    ],
    ids=["with_restrictions", "with_access_conditions", "with_use_conditions"],
)
def test_upload_to_archivespace_gets_mets_if_needed(mocker, params):
    mocker.patch("upload_archivesspace.get_pairs")
    logger = mocker.patch("upload_archivesspace.logger")
    mets_file_mock = mocker.patch("upload_archivesspace.mets_file")
    upload_archivesspace.upload_to_archivesspace(
        [],
        "",
        "",
        "",
        "",
        "",
        "",
        "dipuuid",
        params["access_conditions"],
        params["use_conditions"],
        params["restrictions"],
        # TODO: use os.path.join to make this trailing slash optional
        "/dip/location/path/",
        "",
    )
    mets_file_mock.assert_called_once_with("/dip/location/path/METS.dipuuid.xml")
    logger.debug.assert_has_calls(
        [
            mocker.call("Looking for mets: dipuuid"),
            mocker.call("Found mets file at path: /dip/location/path/METS.dipuuid.xml"),
        ]
    )


def test_upload_to_archivespace_logs_files_with_no_pairs(db, mocker):
    file1_uuid = uuid.uuid4()
    file2_uuid = uuid.uuid4()
    file3_uuid = uuid.uuid4()
    mocker.patch(
        "upload_archivesspace.get_pairs",
        return_value={str(file1_uuid): "myresource", str(file3_uuid): "myresource"},
    )
    logger = mocker.patch("upload_archivesspace.logger")
    mocker.patch("upload_archivesspace.mets_file")
    client_mock = mocker.Mock()
    files = [
        "/path/to/{}-image.jpg".format(file1_uuid),
        "/path/to/{}-video.avi".format(file2_uuid),
        "/path/to/{}-audio.mp3".format(file3_uuid),
    ]
    restrictions = "no"
    upload_archivesspace.upload_to_archivesspace(
        files, client_mock, "", "", "", "", "", "", "", "", restrictions, "", ""
    )
    logger.warning.assert_called_once_with(
        "Skipping file {} ({}) - no pairing found".format(files[1], file2_uuid)
    )


def test_call(db, mocker):
    parser_mock = mocker.Mock(
        **{
            "parse_args.return_value": mocker.Mock(
                **{
                    "base_url": "some_base_url",
                    "user": "some_user",
                    "passwd": "some_passwd",
                    "dip_location": "some_dip_location",
                    "dip_name": "some_dip_name",
                    "dip_uuid": "some_dip_uuid",
                    "xlink_show": "some_xlink_show",
                    "xlink_actuate": "some_xlink_actuate",
                    "object_type": "some_object_type",
                    "use_statement": "some_use_statement",
                    "uri_prefix": "some_uri_prefix",
                    "access_conditions": "some_access_conditions",
                    "use_conditions": "some_use_conditions",
                    "restrictions": "some_restrictions",
                    "inherit_notes": "some_inherit_notes",
                }
            )
        }
    )
    mocker.patch("upload_archivesspace.get_parser", return_value=parser_mock)
    client_mock = mocker.Mock()
    client_factory_mock = mocker.patch(
        "upload_archivesspace.ArchivesSpaceClient", return_value=client_mock
    )
    get_files_from_dip_mock = mocker.patch(
        "upload_archivesspace.get_files_from_dip", return_value=[]
    )
    upload_to_archivesspace = mocker.patch(
        "upload_archivesspace.upload_to_archivesspace"
    )
    job = mocker.Mock(args=[])
    job.JobContext = mocker.MagicMock()
    upload_archivesspace.call([job])
    client_factory_mock.assert_called_once_with(
        host="some_base_url", user="some_user", passwd="some_passwd"
    )
    get_files_from_dip_mock.assert_called_once_with(
        "some_dip_location", "some_dip_name", "some_dip_uuid"
    )
    upload_to_archivesspace.assert_called_once_with(
        [],
        client_mock,
        "some_xlink_show",
        "some_xlink_actuate",
        "some_object_type",
        "some_use_statement",
        "some_uri_prefix",
        "some_dip_uuid",
        "some_access_conditions",
        "some_use_conditions",
        "some_restrictions",
        "some_dip_location",
        False,
    )


@pytest.mark.parametrize(
    "params",
    [
        {"exception": ValueError("cannot find dip"), "expected_job_status": 2},
        {"exception": Exception("unknown error"), "expected_job_status": 3},
    ],
    ids=["no_files_found", "unknown_error_raised"],
)
def test_call_when_files_from_dip_cant_be_retrieved(db, mocker, params):
    mocker.patch("upload_archivesspace.get_parser")
    mocker.patch("upload_archivesspace.ArchivesSpaceClient")
    mocker.patch(
        "upload_archivesspace.get_files_from_dip", side_effect=params["exception"]
    )
    upload_to_archivesspace = mocker.patch(
        "upload_archivesspace.upload_to_archivesspace"
    )
    job = mocker.Mock(args=[])
    job.JobContext = mocker.MagicMock()
    upload_archivesspace.call([job])
    job.set_status.assert_called_once_with(params["expected_job_status"])
    assert not upload_to_archivesspace.called