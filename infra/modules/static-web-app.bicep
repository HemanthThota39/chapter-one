// Azure Static Web App for the Next.js frontend.
// Free tier covers our expected traffic; upgrade to Standard later if custom domain + private-link needed.

param name string
// SWA only available in a limited set of regions — use centralus as a safe default.
// Does NOT affect latency for end users (SWA is globally distributed via a CDN).
param location string = 'centralus'
param branch string = 'main'
param repoUrl string = 'https://github.com/HemanthThota39/chapter-one'
param backendApiFqdn string = ''

// SKU must be Standard for linkedBackends — Free doesn't support
// "bring your own API". This is the cheapest escape hatch from the
// third-party-cookie-is-blocked-by-Safari-ITP / Chrome-strict-mode
// class of bugs: same-origin proxying via /api/* through the SWA.
resource swa 'Microsoft.Web/staticSites@2024-04-01' = {
  name: name
  location: location
  sku: {
    name: 'Standard'
    tier: 'Standard'
  }
  properties: {
    allowConfigFileUpdates: true
    enterpriseGradeCdnStatus: 'Disabled'
    // We deploy via GitHub Actions rather than SWA's built-in pipeline trigger,
    // so we leave `repositoryUrl`/`branch` unset here. The deployment token is
    // fetched after provisioning and used by the workflow.
  }
}

// Backend linked API — Standard SKU lets the SWA proxy /api/* same-origin
// to a Container App. `backendResourceId` is the ARM resource id of the
// Container App (not an FQDN — module param name is legacy).
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
