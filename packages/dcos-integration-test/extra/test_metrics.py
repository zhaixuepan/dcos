import retrying


LATENCY = 60


def test_metrics_agents_ping(dcos_api_session):
    """ Test that the metrics service is up on masters.
    """
    for agent in dcos_api_session.slaves:
        response = dcos_api_session.metrics.get('ping', node=agent)
        assert response.status_code == 200, 'Status code: {}, Content {}'.format(response.status_code, response.content)
        assert response.json()['ok'], 'Status code: {}, Content {}'.format(response.status_code, response.content)
        'agent.'

    for agent in dcos_api_session.public_slaves:
        response = dcos_api_session.metrics.get('ping', node=agent)
        assert response.status_code == 200, 'Status code: {}, Content {}'.format(response.status_code, response.content)
        assert response.json()['ok'], 'Status code: {}, Content {}'.format(response.status_code, response.content)


def test_metrics_masters_ping(dcos_api_session):
    for master in dcos_api_session.masters:
        response = dcos_api_session.metrics.get('ping', node=master)
        assert response.status_code == 200, 'Status code: {}, Content {}'.format(response.status_code, response.content)
        assert response.json()['ok'], 'Status code: {}, Content {}'.format(response.status_code, response.content)


def test_metrics_node(dcos_api_session):
    """Test that the '/system/v1/metrics/v0/node' endpoint returns the expected
    metrics and metric metadata.
    """
    def expected_datapoint_response(response):
        """Enure that the "node" endpoint returns a "datapoints" dict.
        """
        assert 'datapoints' in response, '"datapoints" dictionary not found'
        'in response, got {}'.format(response)

        for dp in response['datapoints']:
            assert 'name' in dp, '"name" parameter should not be empty, got {}'.format(dp)
            if 'filesystem' in dp['name']:
                assert 'tags' in dp, '"tags" key not found, got {}'.format(dp)

                assert 'path' in dp['tags'], ('"path" tag not found for filesystem metric, '
                                              'got {}'.format(dp))

                assert len(dp['tags']['path']) > 0, ('"path" tag should not be empty for '
                                                     'filesystem metrics, got {}'.format(dp))

        return True

    def expected_dimension_response(response):
        """Ensure that the "node" endpoint returns a dimensions dict that
        contains a non-empty string for cluster_id.
        """
        assert 'dimensions' in response, '"dimensions" object not found in'
        'response, got {}'.format(response)

        assert 'cluster_id' in response['dimensions'], '"cluster_id" key not'
        'found in dimensions, got {}'.format(response)

        assert response['dimensions']['cluster_id'] != "", 'expected cluster to contain a value'

        return True

    # private agents
    for agent in dcos_api_session.slaves:
        response = dcos_api_session.metrics.get('node', node=agent)

        assert response.status_code == 200, 'Status code: {}, Content {}'.format(
            response.status_code, response.content)
        assert expected_datapoint_response(response.json())
        assert expected_dimension_response(response.json())

    # public agents
    for agent in dcos_api_session.public_slaves:
        response = dcos_api_session.metrics.get('node', node=agent)

        assert response.status_code == 200, 'Status code: {}, Content {}'.format(
            response.status_code, response.content)
        assert expected_datapoint_response(response.json())
        assert expected_dimension_response(response.json())

    # masters
    for master in dcos_api_session.masters:
        response = dcos_api_session.metrics.get('node', node=master)

        assert response.status_code == 200, 'Status code: {}, Content {}'.format(
            response.status_code, response.content)
        assert expected_datapoint_response(response.json())
        assert expected_dimension_response(response.json())


def test_metrics_containers(dcos_api_session):
    """If there's a deployed container on the slave, iterate through them to check for
    the statsd-emitter executor. When found, query it's /app endpoint to test that
    it's sending the statsd metrics as expected.
    """
    @retrying.retry(wait_fixed=2000, stop_max_delay=LATENCY * 1000)
    def test_containers(app_endpoints):
        for agent in app_endpoints:
            response = dcos_api_session.metrics.get('containers', node=agent.host)
            if len(response.json()) > 0:
                for c in response.json():

                    # Test that /containers/<id> responds with expected data
                    container_response = dcos_api_session.metrics.get('containers/{}'.format(c), node=agent.host)
                    if container_response.status_code == 200 and 'executor_id' in container_response.json():
                        # Executor ID value is "executor_id": "statsd-emitter.a094eed0-b017-11e6-a972-b2bcad3866cb"
                        assert 'statsd-emitter' in container_response.json()['executor_id'].split('.'), 'statsd-emitter'
                        ' was not found running on any slaves.'

                        # Test that /app response is responding with expected data
                        app_response = dcos_api_session.metrics.get('containers/{}/app'.format(c), node=agent.host)
                        if app_response.status_code == 200:
                            assert 'labels' in app_response.json(), '"labels" key not found in response.'
                            assert 'test_tag_key' in container_response.json()['labels'].items(), 'test-tag-key was not'
                            ' found in labels for statsd-emitter, expected test-tag-key key to be present.'

    marathon_config = {
        "id": "/statsd-emitter",
        "cmd": "/opt/mesosphere/bin/./statsd-emitter -debug",
        "cpus": 0.5,
        "mem": 128.0,
        "instances": 1
    }
    with dcos_api_session.marathon.deploy_and_cleanup(marathon_config, check_health=False) as app:
        assert len(app) == 1, 'The marathon app should have been deployed exactly once.'
        test_containers(app)
