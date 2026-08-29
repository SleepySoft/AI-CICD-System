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
  }
  post {
    always { echo "组件自检完成: ${currentBuild.currentResult}" }
  }
}
