// Azure Static Web App for the Next.js frontend.
// Free tier covers our expected traffic; upgrade to Standard later if custom domain + private-link needed.

param name string
// SWA only available in a limited set of regions — use centralus as a safe default.
// Does NOT affect latency for end users (SWA is globally distributed via a CDN).
param location string = 'centralus'
param branch string = 'main'
param repoUrl string = 'https://github.com/HemanthThota39/chapter-one'
param backendApiFqdn string = ''

resource swa 'Microsoft.Web/staticSites@2024-04-01' = {
  name: name
  location: location
  sku: {
    name: 'Free'
    tier: 'Free'
  }
  properties: {
    allowConfigFileUpdates: true
    enterpriseGradeCdnStatus: 'Disabled'
    // We deploy via GitHub Actions rather than SWA's built-in pipeline trigger,
    // so we leave `repositoryUrl`/`branch` unset here. The deployment token is
    // fetched after provisioning and used by the workflow.
  }
}

// Backend linked API (once CA is ready). Optional — enables /api/* routing on same origin.
resource linkedBackend 'Microsoft.Web/staticSites/linkedBackends@2024-04-01' = if (!empty(backendApiFqdn)) {
  parent: swa
  name: 'backend-api'
  properties: {
    backendResourceId: backendApiFqdn
    region: 'centralindia'
  }
}

output id string = swa.id
output name string = swa.name
output defaultHostname string = swa.properties.defaultHostname
