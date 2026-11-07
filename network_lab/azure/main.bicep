param location string = resourceGroup().location
param prefix string = 'desk-link-lab'
@description('Existing SSH public key. Never commit a private key.')
param sshPublicKey string
@description('Caller public IP with /32. No unrestricted management ports.')
param clientCidr string
param administrator string = 'desklab'
resource security 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
 name: '${prefix}-nsg'
 location: location
 properties: {
  securityRules: [{
   name: 'tls-probes'
   properties: { priority: 100, direction: 'Inbound', access: 'Allow', protocol: 'Tcp', sourcePortRange: '*', destinationPortRange: '443', sourceAddressPrefix: clientCidr, destinationAddressPrefix: '*' }
  }]
 }
}
resource network 'Microsoft.Network/virtualNetworks@2024-05-01' = {
 name: '${prefix}-net'
 location: location
 properties: { addressSpace: {addressPrefixes:['10.81.0.0/16']}, subnets:[{name:'nodes',properties:{addressPrefix:'10.81.0.0/24',networkSecurityGroup:{id:security.id}}}] }
}
resource ips 'Microsoft.Network/publicIPAddresses@2024-05-01' = [for i in range(0,2):{
 name:'${prefix}-${i}-ip'
 location:location
 sku:{name:'Standard'}
 properties:{publicIPAllocationMethod:'Static'}
}]
resource interfaces 'Microsoft.Network/networkInterfaces@2024-05-01' = [for i in range(0,2):{
 name:'${prefix}-${i}-nic'
 location:location
 properties:{ipConfigurations:[{name:'node',properties:{privateIPAllocationMethod:'Dynamic',subnet:{id:'${network.id}/subnets/nodes'},publicIPAddress:{id:ips[i].id}}}]}
}]
resource nodes 'Microsoft.Compute/virtualMachines@2024-07-01' = [for i in range(0,2):{
 name:'${prefix}-${i}'
 location:location
 properties:{
  hardwareProfile:{vmSize:'Standard_B1s'}
  storageProfile:{imageReference:{publisher:'Canonical',offer:'ubuntu-24_04-lts',sku:'server',version:'latest'},osDisk:{createOption:'FromImage',managedDisk:{storageAccountType:'Standard_LRS'}}}
  osProfile:{computerName:'desk-node-${i}',adminUsername:administrator,linuxConfiguration:{disablePasswordAuthentication:true,ssh:{publicKeys:[{path:'/home/${administrator}/.ssh/authorized_keys',keyData:sshPublicKey}]}},customData:base64(loadTextContent('cloud-init.yaml'))}
  networkProfile:{networkInterfaces:[{id:interfaces[i].id}]}
 }
}]
output addresses array = [for i in range(0,2):ips[i].properties.ipAddress]
