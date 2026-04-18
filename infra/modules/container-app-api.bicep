// Backend API Container App
// - Ingress on 8000, HTTPS only with managed cert
// - Managed identity-based ACR pull + Key Vault secret refs
// - Env vars + secretRefs wire the app to AI Foundry + App Insights

param location string
param name string
param environmentId string
param image string
param managedIdentityId string
param keyVaultName string
param acrLoginServer string
param minReplicas int = 0
param maxReplicas int = 3
@description('Target container port. Use 80 for the hello-world placeholder; 8000 for our real backend.')
param targetPort int = 80
@description('Health check path. Our backend exposes /health; the placeholder exposes /.')
param healthPath string = '/'
@secure()
param appInsightsConnectionString string
param env string
param aiFoundryEndpoint string
param aiFoundryDeployment string
param aiFoundryApiVersion string
@description('Blob storage account URL, e.g. https://coprodblob01.blob.core.windows.net')
param blobEndpoint string = ''
@description('Static Web App hostname for CORS allow-list (no scheme). Empty means omit.')
param frontendHostname string = ''

@description('Container Apps Environment default domain, to compose our own FQDN for API_BASE_URL.')
param environmentDefaultDomain string

@description('Service Bus namespace hostname for queue dispatch.')
param serviceBusNamespace string = ''

@description('Service Bus queue name for analysis jobs.')
param serviceBusQueueAnalyses string = 'analyses.submitted'

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  properties: {
    environmentId: environmentId
    configuration: {
      ingress: {
        external: true
        targetPort: targetPort
        transport: 'auto'
        allowInsecure: false
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
        corsPolicy: {
          allowedOrigins: [
            'https://*.azurestaticapps.net'
            'http://localhost:3000'
          ]
          allowedMethods: [ 'GET', 'POST', 'PATCH', 'DELETE', 'OPTIONS' ]
          allowedHeaders: [ 'Content-Type', 'Authorization', 'Idempotency-Key', 'Last-Event-ID' ]
          allowCredentials: true
          maxAge: 3600
        }
      }
      registries: [
        {
          server: acrLoginServer
          identity: managedIdentityId
        }
      ]
      secrets: [
        {
          name: 'appinsights-connection-string'
          value: appInsightsConnectionString
        }
        {
          name: 'azure-openai-api-key'
          keyVaultUrl: 'https://${keyVaultName}${environment().suffixes.keyvaultDns}/secrets/azure-openai-api-key'
          identity: managedIdentityId
        }
        {
          name: 'database-url'
          keyVaultUrl: 'https://${keyVaultName}${environment().suffixes.keyvaultDns}/secrets/postgres-connection-string'
          identity: managedIdentityId
        }
        {
          name: 'session-encryption-key'
          keyVaultUrl: 'https://${keyVaultName}${environment().suffixes.keyvaultDns}/secrets/session-encryption-key'
          identity: managedIdentityId
        }
        {
          name: 'entra-tenant-id'
          keyVaultUrl: 'https://${keyVaultName}${environment().suffixes.keyvaultDns}/secrets/entra-tenant-id'
          identity: managedIdentityId
        }
        {
          name: 'entra-tenant-subdomain'
          keyVaultUrl: 'https://${keyVaultName}${environment().suffixes.keyvaultDns}/secrets/entra-tenant-subdomain'
          identity: managedIdentityId
        }
        {
          name: 'entra-client-id'
          keyVaultUrl: 'https://${keyVaultName}${environment().suffixes.keyvaultDns}/secrets/entra-client-id'
          identity: managedIdentityId
        }
        {
          name: 'entra-client-secret'
          keyVaultUrl: 'https://${keyVaultName}${environment().suffixes.keyvaultDns}/secrets/entra-client-secret'
          identity: managedIdentityId
        }
      ]
      activeRevisionsMode: 'Single'
    }
    template: {
      containers: [
        {
          name: 'api'
          image: image
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            { name: 'CHAPTER_ONE_ENV', value: env }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'appinsights-connection-string' }
            { name: 'AZURE_OPENAI_ENDPOINT', value: aiFoundryEndpoint }
            { name: 'AZURE_OPENAI_DEPLOYMENT', value: aiFoundryDeployment }
            { name: 'AZURE_OPENAI_API_VERSION', value: aiFoundryApiVersion }
            { name: 'AZURE_OPENAI_API_KEY', secretRef: 'azure-openai-api-key' }
            { name: 'LOG_IDEA_TEXT', value: 'false' }
            { name: 'LOG_RAW_RESPONSES', value: 'true' }
            { name: 'RESEARCH_CONCURRENCY', value: '4' }
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'SESSION_ENCRYPTION_KEY', secretRef: 'session-encryption-key' }
            { name: 'ENTRA_TENANT_ID', secretRef: 'entra-tenant-id' }
            { name: 'ENTRA_TENANT_SUBDOMAIN', secretRef: 'entra-tenant-subdomain' }
            { name: 'ENTRA_CLIENT_ID', secretRef: 'entra-client-id' }
            { name: 'ENTRA_CLIENT_SECRET', secretRef: 'entra-client-secret' }
            { name: 'BLOB_ENDPOINT', value: blobEndpoint }
            { name: 'API_BASE_URL', value: 'https://${name}.${environmentDefaultDomain}' }
            { name: 'FRONTEND_BASE_URL', value: empty(frontendHostname) ? 'http://localhost:3000' : 'https://${frontendHostname}' }
            { name: 'CORS_ORIGINS', value: empty(frontendHostname) ? 'http://localhost:3000' : 'https://${frontendHostname},http://localhost:3000' }
            { name: 'SERVICE_BUS_NAMESPACE', value: serviceBusNamespace }
            { name: 'SERVICE_BUS_QUEUE_ANALYSES', value: serviceBusQueueAnalyses }
          ]
          probes: [
            {
              type: 'Startup'
              httpGet: { path: healthPath, port: targetPort }
              initialDelaySeconds: 5
              periodSeconds: 5
              failureThreshold: 30
            }
            {
              type: 'Liveness'
              httpGet: { path: healthPath, port: targetPort }
              periodSeconds: 30
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-scale'
            http: {
              metadata: {
                concurrentRequests: '20'
              }
            }
          }
        ]
      }
    }
  }
}

output id string = app.id
output fqdn string = app.properties.configuration.ingress.fqdn
output name string = app.name
