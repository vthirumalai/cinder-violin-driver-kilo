# Copyright 2016 Violin Memory, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
Tests for Violin Memory 6000 Series All-Flash Array Fibrechannel Driver
"""

import mock

from cinder.db.sqlalchemy import models
from cinder import test
from cinder.tests import fake_vmem_xgtools_client as vmemclient
from cinder.volume import configuration as conf
from cinder.volume.drivers.violin import v7000_common
from cinder.volume.drivers.violin import v7000_fcp

VOLUME_ID = "abcdabcd-1234-abcd-1234-abcdeffedcba"
VOLUME = {
    "name": "volume-" + VOLUME_ID,
    "id": VOLUME_ID,
    "display_name": "fake_volume",
    "size": 2,
    "host": "myhost",
    "volume_type": None,
    "volume_type_id": None,
}
SNAPSHOT_ID = "abcdabcd-1234-abcd-1234-abcdeffedcbb"
SNAPSHOT = {
    "name": "snapshot-" + SNAPSHOT_ID,
    "id": SNAPSHOT_ID,
    "volume_id": VOLUME_ID,
    "volume_name": "volume-" + VOLUME_ID,
    "volume_size": 2,
    "display_name": "fake_snapshot",
    "volume": VOLUME,
}
SRC_VOL_ID = "abcdabcd-1234-abcd-1234-abcdeffedcbc"
SRC_VOL = {
    "name": "volume-" + SRC_VOL_ID,
    "id": SRC_VOL_ID,
    "display_name": "fake_src_vol",
    "size": 2,
    "host": "myhost",
    "volume_type": None,
    "volume_type_id": None,
}
INITIATOR_IQN = "iqn.1111-22.org.debian:11:222"
CONNECTOR = {
    "initiator": INITIATOR_IQN,
    "host": "irrelevant",
    'wwpns': ['50014380186b3f65', '50014380186b3f67'],
}
FC_TARGET_WWPNS = [
    '31000024ff45fb22', '21000024ff45fb23',
    '51000024ff45f1be', '41000024ff45f1bf'
]
FC_INITIATOR_WWPNS = [
    '50014380186b3f65', '50014380186b3f67'
]
FC_FABRIC_MAP = {
    'fabricA':
    {'target_port_wwn_list': [FC_TARGET_WWPNS[0], FC_TARGET_WWPNS[1]],
     'initiator_port_wwn_list': [FC_INITIATOR_WWPNS[0]]},
    'fabricB':
    {'target_port_wwn_list': [FC_TARGET_WWPNS[2], FC_TARGET_WWPNS[3]],
     'initiator_port_wwn_list': [FC_INITIATOR_WWPNS[1]]}
}
FC_INITIATOR_TARGET_MAP = {
    FC_INITIATOR_WWPNS[0]: [FC_TARGET_WWPNS[0], FC_TARGET_WWPNS[1]],
    FC_INITIATOR_WWPNS[1]: [FC_TARGET_WWPNS[2], FC_TARGET_WWPNS[3]]
}

GET_VOLUME_STATS_RESPONSE = {
    'vendor_name': 'Violin Memory, Inc.',
    'reserved_percentage': 0,
    'QoS_support': False,
    'free_capacity_gb': 4094,
    'total_capacity_gb': 2558,
}

# The FC_INFO dict returned by the backend is keyed on
# object_id of the FC adapter and the values are the
# wwmns
FC_INFO = {
    '1a3cdb6a-383d-5ba6-a50b-4ba598074510': ['2100001b9745e25e'],
    '4a6bc10a-5547-5cc0-94f2-76222a8f8dff': ['2100001b9745e230'],
    'b21bfff5-d89e-51ff-9920-d990a061d722': ['2100001b9745e25f'],
    'b508cc6b-f78a-51f9-81cf-47c1aaf53dd1': ['2100001b9745e231']
}

CLIENT_INFO = {
    'FCPolicy':
    {'AS400enabled': False,
     'VSAenabled': False,
     'initiatorWWPNList':
     ['50-01-43-80-18-6b-3f-66',
      '50-01-43-80-18-6b-3f-64']},
    'FibreChannelDevices':
    [{'access': 'ReadWrite',
      'id': 'v0000004',
      'initiatorWWPN': '*',
      'lun': '8',
      'name': 'abcdabcd-1234-abcd-1234-abcdeffedcba',
      'sizeMB': 10240,
      'targetWWPN': '*',
      'type': 'SAN'}]
}


CLIENT_INFO1 = {
    'FCPolicy':
    {'AS400enabled': False,
     'VSAenabled': False,
     'initiatorWWPNList':
     ['50-01-43-80-18-6b-3f-66',
      '50-01-43-80-18-6b-3f-64']},
    'FibreChannelDevices':
    [{'access': 'ReadWrite',
      'id': 'v0000004',
      'initiatorWWPN': '*',
      'name': 'xyz',
      'sizeMB': 10240,
      'targetWWPN': '*',
      'type': 'SAN'}]
}


class V7000FCPDriverTestCase(test.TestCase):
    """Test cases for VMEM FCP driver."""
    def setUp(self):
        super(V7000FCPDriverTestCase, self).setUp()
        self.conf = self.setup_configuration()
        self.driver = v7000_fcp.V7000FCPDriver(configuration=self.conf)
        self.driver.common.container = 'myContainer'
        self.driver.device_id = 'ata-VIOLIN_MEMORY_ARRAY_23109R00000022'
        self.driver.gateway_fc_wwns = FC_TARGET_WWPNS
        self.stats = {}
        self.driver.set_initialized()

    def tearDown(self):
        super(V7000FCPDriverTestCase, self).tearDown()

    def setup_configuration(self):
        config = mock.Mock(spec=conf.Configuration)
        config.volume_backend_name = 'v7000_fcp'
        config.san_ip = '8.8.8.8'
        config.san_login = 'admin'
        config.san_password = ''
        config.san_thin_provision = False
        config.san_is_local = False
        config.use_igroups = False
        config.request_timeout = 300
        config.container = 'myContainer'
        return config

    def setup_mock_concerto(self, m_conf=None):
        """Create a fake Concerto communication object."""
        _m_concerto = mock.Mock(name='Concerto',
                                version='1.1.1',
                                spec=vmemclient.mock_client_conf)

        if m_conf:
            _m_concerto.configure_mock(**m_conf)

        return _m_concerto

    @mock.patch.object(v7000_common.V7000Common, 'check_for_setup_error')
    def test_check_for_setup_error(self, m_setup_func):
        """No setup errors are found."""
        result = self.driver.check_for_setup_error()
        m_setup_func.assert_called_with()
        self.assertTrue(result is None)

    @mock.patch.object(v7000_common.V7000Common, 'check_for_setup_error')
    def test_check_for_setup_error_no_wwn_config(self, m_setup_func):
        """No wwns were found during setup."""
        self.driver.gateway_fc_wwns = []
        self.assertRaises(v7000_common.InvalidBackendConfig,
                          self.driver.check_for_setup_error)

    def test_create_volume(self):
        """Volume created successfully."""
        self.driver.common._create_lun = mock.Mock()

        result = self.driver.create_volume(VOLUME)

        self.driver.common._create_lun.assert_called_with(VOLUME)
        self.assertTrue(result is None)

    def test_create_volume_from_snapshot(self):
        self.driver.common._create_volume_from_snapshot = mock.Mock()

        result = self.driver.create_volume_from_snapshot(VOLUME, SNAPSHOT)

        self.driver.common._create_volume_from_snapshot.assert_called_with(
            SNAPSHOT, VOLUME)

        self.assertTrue(result is None)

    def test_create_cloned_volume(self):
        self.driver.common._create_lun_from_lun = mock.Mock()

        result = self.driver.create_cloned_volume(VOLUME, SRC_VOL)

        self.driver.common._create_lun_from_lun.assert_called_with(
            SRC_VOL, VOLUME)
        self.assertTrue(result is None)

    def test_delete_volume(self):
        """Volume deleted successfully."""
        self.driver.common._delete_lun = mock.Mock()

        result = self.driver.delete_volume(VOLUME)

        self.driver.common._delete_lun.assert_called_with(VOLUME)
        self.assertTrue(result is None)

    def test_extend_volume(self):
        """Volume extended successfully."""
        new_size = 10
        self.driver.common._extend_lun = mock.Mock()

        result = self.driver.extend_volume(VOLUME, new_size)

        self.driver.common._extend_lun.assert_called_with(VOLUME, new_size)
        self.assertTrue(result is None)

    def test_create_snapshot(self):
        self.driver.common._create_lun_snapshot = mock.Mock()

        result = self.driver.create_snapshot(SNAPSHOT)
        self.driver.common._create_lun_snapshot.assert_called_with(SNAPSHOT)
        self.assertTrue(result is None)

    def test_delete_snapshot(self):
        self.driver.common._delete_lun_snapshot = mock.Mock()

        result = self.driver.delete_snapshot(SNAPSHOT)
        self.driver.common._delete_lun_snapshot.assert_called_with(SNAPSHOT)
        self.assertTrue(result is None)

    def test_get_volume_stats(self):
        self.driver._update_volume_stats = mock.Mock()
        self.driver._update_volume_stats()

        result = self.driver.get_volume_stats(True)

        self.driver._update_volume_stats.assert_called_with()
        self.assertEqual(self.driver.stats, result)

    def test_update_volume_stats(self):
        """Makes a mock query to the backend to collect
           stats on all physical devices.
        """
        backend_name = self.conf.volume_backend_name

        self.driver.common._get_volume_stats = mock.Mock(
            return_value=GET_VOLUME_STATS_RESPONSE,
        )

        result = self.driver._update_volume_stats()

        self.driver.common._get_volume_stats.assert_called_with(
            self.conf.san_ip)
        self.assertEqual(backend_name,
                         self.driver.stats['volume_backend_name'])
        self.assertEqual('fibre_channel',
                         self.driver.stats['storage_protocol'])
        self.assertTrue(result is None)

    def test_get_active_fc_targets(self):
        """Makes a mock query to the backend to collect
           all the physical adapters and extract the WWNs
        """

        conf = {
            'adapter.get_fc_info.return_value': FC_INFO,
        }

        self.driver.common.vmem_mg = self.setup_mock_concerto(m_conf=conf)

        result = self.driver._get_active_fc_targets()

        self.assertEqual(result, ['2100001b9745e230', '2100001b9745e25f',
                                  '2100001b9745e231', '2100001b9745e25e'])

    def test_convert_wwns_openstack_to_vmem(self):
        vmem_wwns = ['50-01-43-80-18-6b-3f-65']
        openstack_wwns = ['50014380186b3f65']
        result = self.driver._convert_wwns_openstack_to_vmem(openstack_wwns)
        self.assertEqual(vmem_wwns, result)

    def test_convert_wwns_vmem_to_openstack(self):
        vmem_wwns = ['50-01-43-80-18-6b-3f-65']
        openstack_wwns = ['50014380186b3f65']
        result = self.driver._convert_wwns_vmem_to_openstack(vmem_wwns)
        self.assertEqual(openstack_wwns, result)

    def test_initialize_connection(self):
        lun_id = 1
        volume = mock.Mock(spec=models.Volume)

        self.driver.vmem_mg = self.setup_mock_concerto()
        self.driver._export_lun = mock.Mock(return_value=lun_id)

        props = self.driver.initialize_connection(volume, CONNECTOR)

        self.driver._export_lun.assert_called_with(volume, CONNECTOR)
        self.assertEqual(props['driver_volume_type'], "fibre_channel")
        self.assertEqual(props['data']['target_discovered'], True)
        self.assertEqual(props['data']['target_wwn'],
                         self.driver.gateway_fc_wwns)
        self.assertEqual(props['data']['target_lun'], lun_id)

    def test_terminate_connection(self):
        volume = mock.Mock(spec=models.Volume)

        self.driver.vmem_mg = self.setup_mock_concerto()
        self.driver._unexport_lun = mock.Mock()

        result = self.driver.terminate_connection(volume, CONNECTOR)

        self.driver._unexport_lun.assert_called_with(volume, CONNECTOR)
        self.assertEqual(result, None)

    def test_export_lun(self):
        lun_id = '1'
        response = {'success': True, 'msg': 'Assign SAN client successfully'}

        conf = {
            'client.get_client_info.return_value': CLIENT_INFO,
        }
        self.driver.common.vmem_mg = self.setup_mock_concerto(m_conf=conf)

        self.driver.common._send_cmd_and_verify = mock.Mock(
            return_value=response)

        self.driver._get_lun_id = mock.Mock(return_value=lun_id)

        result = self.driver._export_lun(VOLUME, CONNECTOR)

        self.driver.common._send_cmd_and_verify.assert_called_with(
            self.driver.common.vmem_mg.lun.assign_lun_to_client,
            self.driver._is_lun_id_ready,
            'Assign SAN client successfully',
            [VOLUME['id'], CONNECTOR['host'], "ReadWrite"],
            [VOLUME['id'], CONNECTOR['host']])
        self.driver._get_lun_id.assert_called_with(
            VOLUME['id'], CONNECTOR['host'])
        self.assertEqual(lun_id, result)

    def test_export_lun_fails_with_exception(self):
        lun_id = '1'
        response = {'status': False, 'msg': 'Generic error'}

        self.driver.common.vmem_mg = self.setup_mock_concerto()
        self.driver.common._send_cmd_and_verify = mock.Mock(
            side_effect=v7000_common.ViolinBackendErr(response['msg']))
        self.driver._get_lun_id = mock.Mock(return_value=lun_id)

        self.assertRaises(v7000_common.ViolinBackendErr,
                          self.driver._export_lun,
                          VOLUME, CONNECTOR)

    def test_unexport_lun(self):
        response = {'success': True, 'msg': 'Unassign SAN client successfully'}

        self.driver.common.vmem_mg = self.setup_mock_concerto()
        self.driver.common._send_cmd = mock.Mock(
            return_value=response)

        result = self.driver._unexport_lun(VOLUME, CONNECTOR)

        self.driver.common._send_cmd.assert_called_with(
            self.driver.common.vmem_mg.lun.unassign_client_lun,
            "Unassign SAN client successfully",
            VOLUME['id'], CONNECTOR['host'], True)
        self.assertTrue(result is None)

    def test_get_lun_id(self):

        conf = {
            'client.get_client_info.return_value': CLIENT_INFO,
        }
        self.driver.common.vmem_mg = self.setup_mock_concerto(m_conf=conf)

        result = self.driver._get_lun_id(VOLUME['id'], CONNECTOR['host'])

        self.assertEqual(8, result)

    def test_is_lun_id_ready(self):
        lun_id = '1'
        self.driver.common.vmem_mg = self.setup_mock_concerto()

        self.driver._get_lun_id = mock.Mock(return_value=lun_id)

        result = self.driver._is_lun_id_ready(
            VOLUME['id'], CONNECTOR['host'])
        self.assertEqual(True, result)
