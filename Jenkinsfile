pipeline {
    agent { label 'inkiron-windows-x64' }
    options {
        skipDefaultCheckout()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '15', artifactNumToKeepStr: '6'))
        copyArtifactPermission('Adaptive-Resource-Monitor/Publish-Release')
        timeout(time: 35, unit: 'MINUTES')
        timestamps()
    }
    triggers { pollSCM('H/5 * * * *') }
    environment {
        PYTHONDONTWRITEBYTECODE = '1'
        PIP_NO_CACHE_DIR = '1'
        PIP_DISABLE_PIP_VERSION_CHECK = '1'
    }
    stages {
        stage('Source checkout and version') {
            steps {
                deleteDir()
                checkout scm
                script {
                    env.ARM_SOURCE_COMMIT = bat(returnStdout: true, script: '@git rev-parse HEAD').trim()
                    env.ARM_VERSION = readFile('VERSION.md').trim()
                    if (!(env.ARM_SOURCE_COMMIT ==~ /[0-9a-f]{40}/) ||
                        !(env.ARM_VERSION ==~ /v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)_(alpha|beta|rc|stable)/)) {
                        error('Invalid Git commit or authoritative VERSION.md.')
                    }
                    currentBuild.description = "${env.ARM_VERSION} · ${env.ARM_SOURCE_COMMIT.take(12)} · internal archive"
                    echo "Native Windows agent ${env.NODE_NAME}, build #${env.BUILD_NUMBER}, ${env.ARM_VERSION}, ${env.ARM_SOURCE_COMMIT}"
                }
            }
        }
        stage('Environment and dependencies') {
            steps {
                bat 'py -3.12 -m venv .ci\\python'
                bat '.ci\\python\\Scripts\\python.exe -m pip install -r requirements-build.txt'
                bat '.ci\\python\\Scripts\\python.exe -m pip check'
                bat 'powershell.exe -NoLogo -NoProfile -NonInteractive -File tools\\prepare_windows_compiler.ps1'
            }
        }
        stage('Regression and native Windows checks') {
            steps {
                bat '.ci\\python\\Scripts\\python.exe -m unittest discover -s tests -v'
                bat '.ci\\python\\Scripts\\python.exe tests\\windows_gui.py --short'
            }
        }
        stage('Native Windows build, installer and portable ZIP') {
            steps {
                bat '.ci\\python\\Scripts\\python.exe tools\\build_windows.py --iscc .ci\\inno\\ISCC.exe --output release\\candidate'
            }
        }
        stage('Native package and executable metadata validation') {
            steps {
                bat '.ci\\python\\Scripts\\python.exe tests\\windows_gui.py --package release\\candidate --portable-only'
            }
        }
        stage('Checksums, signed manifest and receipt') {
            steps {
                withCredentials([string(credentialsId: 'arm-ed25519-release', variable: 'ARM_ED25519_SIGNING_KEY')]) {
                    bat '@.ci\\python\\Scripts\\python.exe tools\\ci_release.py sign release\\candidate %ARM_SOURCE_COMMIT% %BUILD_NUMBER%'
                }
            }
        }
        stage('Artifact verification and archival') {
            steps {
                bat '.ci\\python\\Scripts\\python.exe tools\\ci_release.py verify release\\candidate %ARM_SOURCE_COMMIT% %BUILD_NUMBER%'
                archiveArtifacts artifacts: 'release/candidate/*', fingerprint: true
            }
        }
    }
    post {
        cleanup {
            deleteDir()
            echo 'Removed the ARM build workspace. Verified candidates are stored in Jenkins archival.'
        }
    }
}
