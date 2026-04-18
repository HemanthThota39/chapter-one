// Key Vault with RBAC authorization mode + diagnostic settings

param location string
param name string
param tenantId string
param readerPrincipals array = []
param logAnalyticsId string

// "Key Vault Secrets User" built-in role
var secretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: name
  location: location
  properties: {
    tenantId: tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enablePurgeProtection: null
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
    sku: {
      family: 'A'
      name: 'standard'
    }
  }
}

// Grant each reader principal the "Secrets User" role
resource secretsReaderRoleAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for (principal, i) in readerPrincipals: {
  name: guid(kv.id, principal, secretsUserRoleId)
  scope: kv
  properties: {
    principalId: principal
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', secretsUserRoleId)
  }
}]

resource kvDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-to-la'
  scope: kv
  properties: {
    workspaceId: logAnalyticsId
    logs: [
      {
        categoryGroup: 'audit'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

output id string = kv.id
output vaultUri string = kv.properties.vaultUri
