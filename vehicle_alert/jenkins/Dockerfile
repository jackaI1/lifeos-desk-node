FROM jenkins/jenkins:2.528.3-lts-jdk21
USER root
RUN apt-get update && apt-get install -y --no-install-recommends build-essential cppcheck python3 && rm -rf /var/lib/apt/lists/*
USER jenkins
RUN jenkins-plugin-cli --latest=false --plugins workflow-aggregator:600.vb_57cdd26fdd7 configuration-as-code:1932.v75cb_b_f1b_698d job-dsl:1.90 junit:1319.v000471ca_e5e2 timestamper:1.28 git:5.7.0
COPY configuration.yaml /usr/share/jenkins/ref/casc.yaml
ENV CASC_JENKINS_CONFIG=/usr/share/jenkins/ref/casc.yaml
ENV JAVA_OPTS=-Djenkins.install.runSetupWizard=false
