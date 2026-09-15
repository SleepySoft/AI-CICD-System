// Chronicler 组件自检流水线（FR-MGR-023 CI 化；本仓库自举）
pipeline {
  agent {
    docker {
      image 'aisystem/ci-agent:latest'
      // --deploy 沙箱测试需要 docker CLI 与宿主 sock
      args '-v /var/run/docker.sock:/var/run/docker.sock'
      reuseNode true
    }
  }
  parameters {
    booleanParam(name: 'DEPLOY_TESTS', defaultValue: false, description: '同时跑隔离沙箱部署测试（慢，需拉镜像）')
    booleanParam(name: 'SANDBOX_TESTS', defaultValue: true, description: '沙箱组件入口可达性测试（现拉现建现测现毁，与生产五通道隔离）')
  }
  triggers {
    // 分支轮询兑底（webhook 不可达时 5 分钟内也能发现新提交）
    pollSCM('H/5 * * * *')
  }
  environment {
    // GitHub SSH 私仓认证：宿主挂载密钥（compose 挂载 /run/ssh -> 收权后 .ssh-ro）
    GIT_SSH_COMMAND = 'ssh -i /var/jenkins_home/.ssh-ro/id_rsa -o StrictHostKeyChecking=no'
  }
  stages {
    stage('依赖') {
      steps {
        sh 'pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple -r chronicler/requirements.txt'
      }
    }
    stage('组件契约自检') {
      steps {
        sh 'python -m chronicler test'
      }
    }
    stage('沙箱部署测试') {
      when { expression { return params.DEPLOY_TESTS } }
      steps {
        sh 'python -m chronicler test --deploy --timeout 600'
      }
    }
    stage('沙箱可达性测试') {
      when { expression { return params.SANDBOX_TESTS } }
      steps {
        // 同一 dockerd 上与部署操作互斥；agent 容器经 docker.sock 操作宿主 dockerd，
        // 卷挂载源必须翻译成宿主视角路径（/var/jenkins_home 是 Jenkins 容器内路径）
        lock('docker-sandbox') {
          timeout(time: 40, unit: 'MINUTES') {
            sh '''
              set -e
              JC=$(docker ps --filter label=com.docker.compose.service=jenkins --format '{{.Names}}' | head -n1)
              JH=$(docker inspect "$JC" --format '{{range .Mounts}}{{if eq .Destination "/var/jenkins_home"}}{{.Source}}{{end}}{{end}}' | tr '\\' '/')
              HOST_WORKSPACE="$JH/workspace/$(basename "$WORKSPACE")"
              echo "宿主视角 workspace: $HOST_WORKSPACE"
              python -m chronicler sandbox --workdir .sandbox --junit sandbox-report.xml \
                --timeout 900 --probe-timeout 600 \
                --host-root "$HOST_WORKSPACE" --probe-host host.docker.internal
            '''
          }
        }
      }
      post {
        always { junit 'sandbox-report.xml' }
      }
    }
  }
  post {
    always { echo "组件自检完成: ${currentBuild.currentResult}" }
  }
}
