// Chapter One — top-level Azure deployment
// Deploys a per-environment stack into a pre-created resource group.
//
// Usage:
//   az deployment group create -g co-dev-rg-cin \
//     -f infra/main.bicep -p @infra/envs/dev.parameters.json

targetScope = 'resourceGroup'

@description('Environment name (dev | prod)')
@allowed([ 'dev', 'prod' ])
param env string

@description('Azure region for resources (default: Central India)')
param location string = resourceGroup().location

@description('AI Foundry endpoint (existing resource, not managed by this deployment)')
param aiFoundryEndpoint string

@description('AI Foundry deployment name')
param aiFoundryDeployment string = 'gpt-5.3-chat'

@description('AI Foundry API version')
param aiFoundryApiVersion string = '2025-03-01-preview'

@description('AI Foundry API key — supplied at deploy time, stored immediately in Key Vault')
@secure()
param aiFoundryApiKey string

@description('Container image tag to deploy (backend). Defaults to a public placeholder for first bootstrap.')
param backendImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Container port the backend listens on. Default 80 for placeholder; 8000 for our real backend.')
param targetPort int = 80

@description('HTTP path for liveness/startup probes. Default / for placeholder; /health for our real backend.')
param healthPath string = '/'

@description('Monthly cost cap in INR for this environment. Alerts fire at 50/75/90%.')
param monthlyBudgetInr int = 3000

@description('Email address for budget + ops alerts')
param alertEmail string = 'hemant.thota@gmail.com'

// --- M1 additions ---
@description('Postgres admin password — generated fresh for each env; stored in Key Vault.')
@secure()
param postgresAdminPassword string

@description('Session encryption key (Fernet) for HTTP-only session cookies.')
@secure()
param sessionEncryptionKey string

// ---------------------------------------------------------------------
// Naming
// ---------------------------------------------------------------------
var regionCode = 'cin'
var namePrefix = 'co-${env}'

// Helpers for resources that can't take dashes / have length limits
var acrName        = 'co${env}acr${regionCode}${substring(uniqueString(resourceGroup().id), 0, 6)}'
var kvName         = 'co-${env}-kv-${substring(uniqueString(resourceGroup().id), 0, 6)}'
var laName         = '${namePrefix}-log-${regionCode}'
var aiInsightsName = '${namePrefix}-ai-${regionCode}'
var caeName        = '${namePrefix}-cae-${regionCode}'
var apiAppName     = '${namePrefix}-api-${regionCode}'
var apiMiName      = '${namePrefix}-mi-api-${regionCode}'
var pgName         = '${namePrefix}-pg-${regionCode}'
var blobAccountName = 'co${env}blob${substring(uniqueString(resourceGroup().id), 0, 8)}'
var swaName        = 'co-${env}-web'
var sbNamespaceName = '${namePrefix}-sb-${regionCode}-${substring(uniqueString(resourceGroup().id), 0, 4)}'
var workerJobName   = '${namePrefix}-worker-analysis-${regionCode}'

// ---------------------------------------------------------------------
// Monitoring — LA workspace + App Insights (set up FIRST)
// ---------------------------------------------------------------------
module monitor 'modules/monitor.bicep' = {
  name: 'monitor'
  params: {
    location:            location
    logAnalyticsName:    laName
    appInsightsName:     aiInsightsName
    retentionDays:       30  // PerGB2018 minimum is 30; both envs use the minimum for cost
    dailyCapGb:          1
  }
}

// ---------------------------------------------------------------------
// Managed identity for the API container
// ---------------------------------------------------------------------
module apiIdentity 'modules/identity.bicep' = {
  name: 'api-identity'
  params: {
    location: location
    name: apiMiName
  }
}

// ---------------------------------------------------------------------
// Key Vault — stores AI Foundry key, session key, etc.
// ---------------------------------------------------------------------
module keyVault 'modules/key-vault.bicep' = {
  name: 'key-vault'
  params: {
    location:         location
    name:             kvName
    tenantId:         subscription().tenantId
    readerPrincipals: [
      apiIdentity.outputs.principalId
    ]
    logAnalyticsId:   monitor.outputs.logAnalyticsId
  }
}

// Initial secret: AI Foundry API key
resource kvRef 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: kvName
  dependsOn: [ keyVault ]
}

resource secretAiFoundryKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kvRef
  name: 'azure-openai-api-key'
  properties: {
    value: aiFoundryApiKey
    attributes: { enabled: true }
  }
}

resource secretPgPassword 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kvRef
  name: 'postgres-admin-password'
  properties: {
    value: postgresAdminPassword
    attributes: { enabled: true }
  }
}

resource secretSessionKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kvRef
  name: 'session-encryption-key'
  properties: {
    value: sessionEncryptionKey
    attributes: { enabled: true }
  }
}

// App Insights connection string stored in KV so the worker can load it via managed identity
resource secretAppInsightsConn 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kvRef
  name: 'appinsights-connection-string'
  properties: {
    value: monitor.outputs.appInsightsConnectionString
    attributes: { enabled: true }
  }
}

// ---------------------------------------------------------------------
// Postgres Flexible Server — relational store
// ---------------------------------------------------------------------
module postgres 'modules/postgres.bicep' = {
  name: 'postgres'
  params: {
    location:        location
    name:            pgName
    env:             env
    logAnalyticsId:  monitor.outputs.logAnalyticsId
    adminPassword:   postgresAdminPassword
    storageGB:       32  // 32 is the minimum for Flexible Server regardless of tier
  }
}

// Build a connection string for the app and stash it as a KV secret so we don't echo it in env vars.
resource secretPgConnection 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kvRef
  name: 'postgres-connection-string'
  properties: {
    value: 'postgresql://${postgres.outputs.adminLogin}:${postgresAdminPassword}@${postgres.outputs.fqdn}:5432/${postgres.outputs.dbName}?sslmode=require'
    attributes: { enabled: true }
  }
  dependsOn: [
    postgres
  ]
}

// ---------------------------------------------------------------------
// Blob Storage — avatars, PDFs, raw agent JSON, per-analysis summaries
// ---------------------------------------------------------------------
module storage 'modules/storage.bicep' = {
  name: 'blob-storage'
  params: {
    location:        location
    name:            blobAccountName
    logAnalyticsId:  monitor.outputs.logAnalyticsId
    blobDataContributorPrincipals: [
      apiIdentity.outputs.principalId
    ]
  }
}

// ---------------------------------------------------------------------
// Static Web App — frontend hosting
// ---------------------------------------------------------------------
module web 'modules/static-web-app.bicep' = {
  name: 'static-web-app'
  params: {
    name: swaName
  }
}

// ---------------------------------------------------------------------
// Service Bus — analysis job queue
// ---------------------------------------------------------------------
module serviceBus 'modules/service-bus.bicep' = {
  name: 'service-bus'
  params: {
    location:        location
    name:            sbNamespaceName
    logAnalyticsId:  monitor.outputs.logAnalyticsId
    sendReceivePrincipals: [
      apiIdentity.outputs.principalId   // API sends; worker (same MI) receives
    ]
  }
}

// ---------------------------------------------------------------------
// Analysis worker — Container Apps Job, queue-triggered
// ---------------------------------------------------------------------
module analysisWorker 'modules/container-app-job.bicep' = {
  name: 'analysis-worker'
  params: {
    name:            workerJobName
    location:        location
    environmentId:   caEnv.outputs.id
    image:           backendImage
    managedIdentityId: apiIdentity.outputs.id
    managedIdentityClientId: apiIdentity.outputs.clientId
    acrLoginServer:  acr.outputs.loginServer
    keyVaultName:    kvName
    triggerType:     'Event'
    serviceBusQueueName: serviceBus.outputs.queueName
    serviceBusNamespaceHostname: '${serviceBus.outputs.namespaceName}.servicebus.windows.net'
    parallelism:     env == 'prod' ? 3 : 1
    replicaCompletionCount: 1
    replicaTimeout:  1800   // 30 min cap per analysis
    replicaRetryLimit: 2
    extraEnvVars: [
      { name: 'CHAPTER_ONE_ENV', value: env }
      { name: 'SERVICE_BUS_NAMESPACE', value: '${serviceBus.outputs.namespaceName}.servicebus.windows.net' }
      { name: 'SERVICE_BUS_QUEUE_ANALYSES', value: serviceBus.outputs.queueName }
      { name: 'BLOB_ENDPOINT', value: storage.outputs.blobEndpoint }
      { name: 'AZURE_OPENAI_ENDPOINT', value: aiFoundryEndpoint }
      { name: 'AZURE_OPENAI_DEPLOYMENT', value: aiFoundryDeployment }
      { name: 'AZURE_OPENAI_API_VERSION', value: aiFoundryApiVersion }
      { name: 'LOG_IDEA_TEXT', value: 'false' }
      { name: 'LOG_RAW_RESPONSES', value: 'true' }
      { name: 'RESEARCH_CONCURRENCY', value: '4' }
      { name: 'WORKER_ROLE', value: 'analysis' }
    ]
    command: [ 'python' ]
    args: [ '-m', 'app.workers.analysis_worker' ]
  }
  dependsOn: [
    secretPgConnection
    secretAiFoundryKey
  ]
}

// ---------------------------------------------------------------------
// Azure Container Registry — private image store
// ---------------------------------------------------------------------
module acr 'modules/acr.bicep' = {
  name: 'acr'
  params: {
    location:   location
    name:       acrName
    pullPrincipals: [ apiIdentity.outputs.principalId ]
    logAnalyticsId: monitor.outputs.logAnalyticsId
  }
}

// ---------------------------------------------------------------------
// Container Apps Environment
// ---------------------------------------------------------------------
module caEnv 'modules/container-apps-env.bicep' = {
  name: 'container-apps-env'
  params: {
    location:              location
    name:                  caeName
    logAnalyticsCustomerId: monitor.outputs.logAnalyticsCustomerId
    logAnalyticsSharedKey:  monitor.outputs.logAnalyticsSharedKey
  }
}

// ---------------------------------------------------------------------
// API Container App
// ---------------------------------------------------------------------
module apiApp 'modules/container-app-api.bicep' = {
  name: 'container-app-api'
  params: {
    location:        location
    name:            apiAppName
    environmentId:   caEnv.outputs.id
    image:           backendImage
    targetPort:      targetPort
    healthPath:      healthPath
    managedIdentityId: apiIdentity.outputs.id
    managedIdentityClientId: apiIdentity.outputs.clientId
    keyVaultName:    kvName
    acrLoginServer:  acr.outputs.loginServer
    minReplicas:     env == 'prod' ? 1 : 0
    maxReplicas:     env == 'prod' ? 3 : 1
    appInsightsConnectionString: monitor.outputs.appInsightsConnectionString
    env:             env
    aiFoundryEndpoint: aiFoundryEndpoint
    aiFoundryDeployment: aiFoundryDeployment
    aiFoundryApiVersion: aiFoundryApiVersion
    blobEndpoint:    storage.outputs.blobEndpoint
    frontendHostname: web.outputs.defaultHostname
    environmentDefaultDomain: caEnv.outputs.defaultDomain
    serviceBusNamespace: '${serviceBus.outputs.namespaceName}.servicebus.windows.net'
    serviceBusQueueAnalyses: serviceBus.outputs.queueName
  }
  dependsOn: [
    secretAiFoundryKey
    secretPgPassword
    secretSessionKey
    secretPgConnection
    secretAppInsightsConn
  ]
}

// ---------------------------------------------------------------------
// Budget + alerts
// ---------------------------------------------------------------------
module budget 'modules/budget.bicep' = {
  name: 'budget'
  params: {
    env:             env
    budgetInr:       monthlyBudgetInr
    contactEmails:   [ alertEmail ]
  }
}

// ---------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------
output apiFqdn string = apiApp.outputs.fqdn
output acrLoginServer string = acr.outputs.loginServer
output keyVaultName string = kvName
output appInsightsName string = aiInsightsName
output apiManagedIdentityPrincipalId string = apiIdentity.outputs.principalId
output postgresFqdn string = postgres.outputs.fqdn
output postgresDb string = postgres.outputs.dbName
output blobEndpoint string = storage.outputs.blobEndpoint
output blobAccountName string = blobAccountName
output frontendHostname string = web.outputs.defaultHostname
output frontendUrl string = 'https://${web.outputs.defaultHostname}'
output serviceBusNamespace string = serviceBus.outputs.namespaceName
output analysisWorkerName string = workerJobName

