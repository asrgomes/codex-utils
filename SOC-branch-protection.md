```humanpy
Load playwright skill, do not load alm-browser-playwright skill, do not use unsafe browser code
Ensure you can open "https://alm.oraclecorp.com/sfp"

def capture(ALM_PROJECT, GIT_REPO, BRANCH_PATTERN):
  Open "https://alm.oraclecorp.com/sfp/#projects/<ALM_PROJECT>/admin/merge/<GIT_REPO>/<BRANCH_PATTERN>?fc=name&ft=&r=<GIT_REPO>"
  Save a screenshot:
    name: "screenshots/(<ALM_PROJECT>) <GIT_REPO> - <ISO_TIMESTAMP>.png"
    add timestamp (UTC) located at the top-right corner (20% tranparent yellow background, 32px margin-top, 15px margin-right)
  Close tab


# capture('vm', 'mpg.git', 'release/**')
# capture('vm', 'vug.git', 'release/**')
# capture('vm', 'dlq-mgr.git', 'release/**')
# capture('vm', 'vm.git', 'release/**')
# capture('vm', 'student-portal.git', 'release/**')
# capture('vm', 'sfp-audit-logging.git', 'release/**')
# capture('vm', 'sfp-customer-configurator.git', 'release/**')
capture('devops', 'sfp-chart.git', 'release/**')
capture('devops', 'metrics-agent.git', 'master')
capture('devops', 'docker-images.git', 'master')
capture('devops', 'jenkins-lib.git', 'master')
capture('devops', 'oracle-bi-images.git', 'master')
capture('devops', 'provisioning.git', 'master')
capture('devops', 'sfp-blueprint.git', 'master')
capture('devops', 'sfp-heartbeat.git', 'master')
capture('devops', 'sfp-idm-integration.git', 'master')

```
