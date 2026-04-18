// Azure Service Bus namespace + `analyses.submitted` queue with dead-letter.
// Standard tier — supports topics for Phase 3 fan-out without migration.

param location string
param name string
param logAnalyticsId string
@description('Managed identities that need to send + receive messages (dev: same MI).')
param sendReceivePrincipals array = []

// Built-in role IDs
var sbDataOwnerId    = '090c5cfd-751d-490a-894a-3ce6f1109419'  // Azure Service Bus Data Owner
var sbDataReceiverId = '4f6d3b9b-027b-4f4c-9142-0e5a2a2247e0'  // Azure Service Bus Data Receiver
var sbDataSenderId   = '69a216fc-b8fb-44d8-bc22-1f3c2cd27a39'  // Azure Service Bus Data Sender

resource sb 'Microsoft.ServiceBus/namespaces@2024-01-01' = {
  name: name
  location: location
  sku: {
    name: 'Standard'
    tier: 'Standard'
  }
  properties: {
    disableLocalAuth: false
    zoneRedundant: false
    publicNetworkAccess: 'Enabled'
  }
}

resource analysesQueue 'Microsoft.ServiceBus/namespaces/queues@2024-01-01' = {
  parent: sb
  name: 'analyses.submitted'
  properties: {
    lockDuration: 'PT5M'           // workers have 5 min to ack / renew; analyses run 3-5 min
    maxDeliveryCount: 3            // 3 tries then dead-letter
    defaultMessageTimeToLive: 'P1D'
    deadLetteringOnMessageExpiration: true
    enableBatchedOperations: true
    enablePartitioning: false
    requiresDuplicateDetection: false
    requiresSession: false
  }
}

// Owner on the namespace: the deployer identity (GH Actions) to manage queues
// (already has Contributor via RG). Data roles assigned below for runtime pods.

resource dataReceiverAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for principal in sendReceivePrincipals: {
  name: guid(sb.id, principal, sbDataReceiverId)
  scope: sb
  properties: {
    principalId: principal
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', sbDataReceiverId)
  }
}]

resource dataSenderAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for principal in sendReceivePrincipals: {
  name: guid(sb.id, principal, sbDataSenderId)
  scope: sb
  properties: {
    principalId: principal
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', sbDataSenderId)
  }
}]

resource sbDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-to-la'
  scope: sb
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

output namespaceName string = sb.name
output namespaceEndpoint string = 'https://${sb.name}.servicebus.windows.net'
output namespaceId string = sb.id
output queueName string = analysesQueue.name
