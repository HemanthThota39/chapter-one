// User-assigned managed identity

param location string
param name string

resource mi 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: name
  location: location
}

output id string = mi.id
output principalId string = mi.properties.principalId
output clientId string = mi.properties.clientId
