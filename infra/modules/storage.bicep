// Blob Storage: avatars (public-read), pdfs, raw agent JSON, per-analysis summaries (all private).
// Managed identities granted Blob Data Contributor on the full account.

param location string
param name string
param logAnalyticsId string
param blobDataContributorPrincipals array = []

// Built-in role IDs
var blobDataContributorId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: name
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: true
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
    publicNetworkAccess: 'Enabled'
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    deleteRetentionPolicy: { enabled: true, days: 7 }
    containerDeleteRetentionPolicy: { enabled: true, days: 7 }
  }
}

resource avatarsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'avatars'
  properties: {
    publicAccess: 'Blob'  // individual blobs readable; listing disabled
  }
}

resource pdfsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'pdfs'
  properties: {
    publicAccess: 'None'  // served via signed URLs or through the backend
  }
}

resource rawContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'raw'
  properties: {
    publicAccess: 'None'  // per-agent JSON dumps
  }
}

resource summariesContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'summaries'
  properties: {
    publicAccess: 'None'  // per-analysis summary.md
  }
}

// Grant Blob Data Contributor to requested principals
resource blobRoleAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for principal in blobDataContributorPrincipals: {
  name: guid(storage.id, principal, blobDataContributorId)
  scope: storage
  properties: {
    principalId: principal
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataContributorId)
  }
}]

resource storageDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-to-la'
  scope: blobService
  properties: {
    workspaceId: logAnalyticsId
    logs: [
      { categoryGroup: 'allLogs', enabled: true }
    ]
    metrics: [
      { category: 'AllMetrics', enabled: true }
    ]
  }
}

output id string = storage.id
output name string = storage.name
output blobEndpoint string = storage.properties.primaryEndpoints.blob
output avatarsContainer string = avatarsContainer.name
output pdfsContainer string = pdfsContainer.name
output rawContainer string = rawContainer.name
output summariesContainer string = summariesContainer.name
