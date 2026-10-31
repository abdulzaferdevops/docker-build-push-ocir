// Lab 4: docker-build-push-ocir
// GitHub push -> Jenkins -> tests inside the image build -> runtime image tagged by commit
// -> container smoke test -> Trivy vulnerability gate -> push to OCI Container Registry
// -> record the immutable digest -> trigger Lab 5 (app-server-podman-deploy) with that digest.
//
// One-time Jenkins setup (see README):
//   - Credential 'ocir-push' (username + auth token)
//   - Global environment variables OCIR_HOST and OCIR_NAMESPACE
//   - Private repository ci-labs/flask-api created in the lab compartment (not auto-created in root)

pipeline {
  agent any

  options {
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '20', artifactNumToKeepStr: '20'))
    timeout(time: 30, unit: 'MINUTES')
  }

  triggers {
    githubPush()
  }

  environment {
    REPO_PATH   = 'ci-labs/flask-api'
    TRIVY_IMAGE = 'aquasec/trivy:0.56.2'
  }

  stages {
    stage('Preflight') {
      steps {
        script {
          ['OCIR_HOST', 'OCIR_NAMESPACE'].each { v ->
            if (!env."${v}"?.trim()) {
              error("${v} is not set: Manage Jenkins > System > Global properties > Environment variables")
            }
          }
          env.SHORT_SHA = sh(script: 'echo "${GIT_COMMIT:-manual}" | cut -c1-7', returnStdout: true).trim()
          env.RELEASE   = sh(script: 'printf "%05d-%s" "$BUILD_NUMBER" "$SHORT_SHA"', returnStdout: true).trim()
          env.IMAGE     = "${env.OCIR_HOST}/${env.OCIR_NAMESPACE}/${env.REPO_PATH}"
          env.LOCAL     = "lab4-flask-api:${env.RELEASE}"
          currentBuild.displayName = "#${env.BUILD_NUMBER} ${env.SHORT_SHA}"
        }
        sh '''
          docker info >/dev/null 2>&1 || { echo "Jenkins cannot use Docker"; exit 1; }
          echo "image will be: $IMAGE:$SHORT_SHA (and :$RELEASE)"
          echo "builder: $(docker buildx version 2>/dev/null || echo 'classic builder')"
          df -h /var/lib/docker 2>/dev/null | tail -1 || true
        '''
      }
    }

    stage('Test in build') {
      steps {
        sh '''
          if grep -rIlE --exclude-dir=.git -e "-----BEGIN [A-Z ]*PRIVATE KEY-----" . ; then
            echo "Refusing to build: a private key is committed in the file(s) above"
            exit 1
          fi
          # Builds only the 'test' stage: flake8 + pytest run inside the image build
          docker build --target test --pull -t "lab4-flask-api:test-$BUILD_NUMBER" .
        '''
      }
    }

    stage('Build image') {
      steps {
        sh '''
          BUILT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
          docker build --target runtime \
            --build-arg RELEASE="$RELEASE" \
            --build-arg COMMIT="${GIT_COMMIT:-unknown}" \
            --build-arg BUILT="$BUILT" \
            -t "$LOCAL" .
          docker image inspect "$LOCAL" --format 'size: {{.Size}} bytes | user: {{.Config.User}} | revision: {{index .Config.Labels "org.opencontainers.image.revision"}}'
        '''
      }
    }

    stage('Container smoke test') {
      steps {
        sh '''
          NAME="lab4-smoke-$BUILD_NUMBER"
          docker rm -f "$NAME" >/dev/null 2>&1 || true
          docker run -d --name "$NAME" --read-only --tmpfs /tmp --cap-drop ALL \
            --security-opt no-new-privileges "$LOCAL" >/dev/null

          # Call the app from inside its own container (no published ports needed)
          for attempt in 1 2 3 4 5 6 7 8 9 10; do
            BODY=$(docker exec "$NAME" python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read().decode())" 2>/dev/null || true)
            if echo "$BODY" | grep -q "\\"release\\":\\"$RELEASE\\""; then
              echo "health: $BODY"
              break
            fi
            sleep 2
          done
          if ! echo "$BODY" | grep -q "\\"release\\":\\"$RELEASE\\""; then
            echo "container did not report release $RELEASE (last: ${BODY:-none})"
            docker logs --tail 30 "$NAME"
            exit 1
          fi

          echo "runs as: $(docker exec "$NAME" id)"
          docker exec "$NAME" python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/items?category=network', timeout=2).read().decode())" | tee smoke.json
          grep -q '"count":' smoke.json
          echo "container smoke test passed"
        '''
      }
      post {
        always {
          sh 'docker rm -f "lab4-smoke-$BUILD_NUMBER" >/dev/null 2>&1 || true'
        }
      }
    }

    stage('Vulnerability scan') {
      steps {
        sh '''
          mkdir -p reports
          # Full report (HIGH + CRITICAL) for the record; never fails the build on its own
          docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v lab4-trivy-cache:/root/.cache \
            "$TRIVY_IMAGE" image --quiet --severity HIGH,CRITICAL --ignore-unfixed \
            --format table "$LOCAL" | tee reports/trivy.txt

          # Gate: fail on HIGH or CRITICAL vulnerabilities that already have a fix available
          docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v lab4-trivy-cache:/root/.cache \
            "$TRIVY_IMAGE" image --quiet --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 \
            --format table "$LOCAL" >/dev/null \
            && echo "vulnerability gate passed: no fixable HIGH or CRITICAL findings" \
            || { echo "vulnerability gate FAILED: fixable HIGH or CRITICAL findings (see report above)"; exit 1; }
        '''
      }
    }

    stage('Push to OCIR') {
      steps {
        withCredentials([usernamePassword(credentialsId: 'ocir-push',
                                          usernameVariable: 'OCIR_USER', passwordVariable: 'OCIR_TOKEN')]) {
          sh '''
            # Temporary Docker config: the login never persists on the Jenkins server
            export DOCKER_CONFIG="$(mktemp -d)"
            trap 'docker logout "$OCIR_HOST" >/dev/null 2>&1; rm -rf "$DOCKER_CONFIG"' EXIT

            printf '%s' "$OCIR_TOKEN" | docker login "$OCIR_HOST" -u "$OCIR_USER" --password-stdin >/dev/null
            echo "logged in to $OCIR_HOST"

            docker tag "$LOCAL" "$IMAGE:$SHORT_SHA"
            docker tag "$LOCAL" "$IMAGE:$RELEASE"
            docker push --quiet "$IMAGE:$SHORT_SHA"
            docker push --quiet "$IMAGE:$RELEASE"

            DIGEST=$(docker image inspect "$IMAGE:$SHORT_SHA" --format '{{range .RepoDigests}}{{println .}}{{end}}' | grep "^$IMAGE@" | head -1)
            [ -n "$DIGEST" ] || { echo "could not determine pushed digest"; exit 1; }
            echo "pushed: $DIGEST"
            printf '{"image":"%s","tag":"%s","release":"%s","digest":"%s","commit":"%s"}\\n' \
              "$IMAGE" "$SHORT_SHA" "$RELEASE" "$DIGEST" "${GIT_COMMIT:-unknown}" > image.json
            cat image.json
            printf '%s' "$DIGEST" > digest.txt
          '''
        }
        script {
          env.PUSHED_DIGEST = readFile('digest.txt').trim()
          currentBuild.description = "pushed ${env.SHORT_SHA} (release ${env.RELEASE})"
        }
        archiveArtifacts artifacts: 'image.json', fingerprint: true
      }
    }
    stage('Deploy (Lab 5)') {
      steps {
        // Same bytes that were tested and scanned above, identified by digest.
        // wait + propagate: this build fails if the deploy (and its automatic rollback) fails.
        build job: 'app-server-podman-deploy', wait: true, propagate: true,
              parameters: [string(name: 'IMAGE_DIGEST', value: env.PUSHED_DIGEST),
                           string(name: 'ACTION', value: 'deploy')]
      }
    }
  }

  post {
    always {
      archiveArtifacts artifacts: 'reports/trivy.txt', allowEmptyArchive: true
      // Keep the Jenkins server's disk tidy: remove this build's local images
      sh '''
        docker rmi -f "lab4-flask-api:test-$BUILD_NUMBER" "lab4-flask-api:$RELEASE" \
          "$IMAGE:$SHORT_SHA" "$IMAGE:$RELEASE" >/dev/null 2>&1 || true
        docker image prune -f --filter "until=24h" >/dev/null 2>&1 || true
        rm -f smoke.json digest.txt
      '''
    }
  }
}
