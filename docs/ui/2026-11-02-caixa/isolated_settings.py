import os
import tempfile

def pytest_configure(config):
    os.environ['XDG_CONFIG_HOME'] = tempfile.mkdtemp(prefix='stockflow-caixa-test-config-')
