pipeline {
    agent { label 'inkiron-windows-x64' }
    options {
        skipDefaultCheckout()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '15', artifactNumToKeepStr: '6'))
        copyArtifactPermission('Publish-Release')
        timeout(time: 35, unit: 'MINUTES')
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
                script {
                    def gitInfo = checkout scm
                    env.ARM_SOURCE_COMMIT = bat(returnStdout: true, script: '@git rev-parse HEAD').trim()
                    env.ARM_VERSION = readFile('VERSION.md').trim()
                    env.PYINSTALLER_CONFIG_DIR = "${env.WORKSPACE}\\.ci\\pyinstaller-cache"
                    if (!(env.ARM_SOURCE_COMMIT ==~ /[0-9a-f]{40}/) ||
                        !(env.ARM_VERSION ==~ /v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)_(alpha|beta|rc|stable)/)) {
                        error('Invalid Git commit or authoritative VERSION.md.')
                    }
                    def previous = gitInfo.GIT_PREVIOUS_SUCCESSFUL_COMMIT
                    def changed = previous ==~ /[0-9a-f]{40}/
                        ? bat(returnStdout: true, script: "@git diff --name-only --no-renames ${previous} ${env.ARM_SOURCE_COMMIT}").readLines().collect { it.trim() }.findAll { it }
                        : []
                    def documentation = { path -> path in ['README.md', 'RELEASE_PROCESS.md',
                        'CONTRIBUTING.md', 'SUPPORT.md', 'SECURITY.md', 'ISSUE_MANAGEMENT.md', 'ROADMAP.md'] ||
                        path.startsWith('docs/screenshots/') || path.startsWith('.gitea/ISSUE_TEMPLATE/') }
                    def documentationWorkflow = ['Jenkinsfile', 'tools/readme_release.py', 'tools/ci_release.py']
                    env.ARM_DOCS_ONLY = (changed.any(documentation) && changed.every { path ->
                        documentation(path) || path in documentationWorkflow
                    }).toString()
                    currentBuild.description = "${env.ARM_VERSION} · ${env.ARM_SOURCE_COMMIT.take(12)} · ${env.ARM_DOCS_ONLY == 'true' ? 'documentation only' : 'internal archive'}"
                    echo "Native Windows agent ${env.NODE_NAME}, build #${env.BUILD_NUMBER}, ${env.ARM_VERSION}, ${env.ARM_SOURCE_COMMIT}"
                }
            }
        }
        stage('Environment and dependencies') {
            when { expression { env.ARM_DOCS_ONLY != 'true' } }
            steps {
                bat 'py -3.12 -m venv .ci\\python'
                bat '.ci\\python\\Scripts\\python.exe -m pip install -r requirements-build.txt'
                bat '.ci\\python\\Scripts\\python.exe -m pip check'
                bat '.ci\\python\\Scripts\\python.exe tools\\prepare_windows_compiler.py'
            }
        }
        stage('Regression and native Windows checks') {
            when { expression { env.ARM_DOCS_ONLY != 'true' } }
            steps {
                bat '.ci\\python\\Scripts\\python.exe -m unittest discover -s tests -v'
                bat '.ci\\python\\Scripts\\python.exe tests\\windows_gui.py --short'
            }
        }
        stage('Native Windows build, installer and portable ZIP') {
            when { expression { env.ARM_DOCS_ONLY != 'true' } }
            steps {
                bat '.ci\\python\\Scripts\\python.exe tools\\build_windows.py --iscc .ci\\inno\\ISCC.exe --output release\\candidate'
            }
        }
        stage('Native package and executable metadata validation') {
            when { expression { env.ARM_DOCS_ONLY != 'true' } }
            steps {
                bat '.ci\\python\\Scripts\\python.exe tests\\windows_gui.py --package release\\candidate --portable-only'
            }
        }
        stage('Checksums, signed manifest and receipt') {
            when { expression { env.ARM_DOCS_ONLY != 'true' } }
            steps {
                withCredentials([string(credentialsId: 'arm-ed25519-release', variable: 'ARM_ED25519_SIGNING_KEY')]) {
                    bat '@.ci\\python\\Scripts\\python.exe tools\\ci_release.py sign release\\candidate %ARM_SOURCE_COMMIT% %BUILD_NUMBER%'
                }
            }
        }
        stage('Artifact verification and archival') {
            when { expression { env.ARM_DOCS_ONLY != 'true' } }
            steps {
                bat '.ci\\python\\Scripts\\python.exe tools\\ci_release.py verify release\\candidate %ARM_SOURCE_COMMIT% %BUILD_NUMBER%'
                archiveArtifacts artifacts: 'release/candidate/*', fingerprint: true
            }
        }
    }
    post {
        cleanup {
            deleteDir()
            echo 'Removed the ARM build workspace. Any successfully archived artifacts remain in Jenkins.'
        }
    }
}
