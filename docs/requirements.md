# Project: Omada Network Documentation Platform

## 1. Project Goal

Develop a complete, modern, web-based documentation platform for TP-Link Omada networks.

The application must connect to an Omada Controller through the official Omada Open API, retrieve its configuration, store the data in a structured format, and generate comprehensive, searchable, and graphically presented network documentation.

The application will run as a standalone Docker container or Docker Compose project on a Synology NAS, managed through Synology Container Manager.

The application is primarily a documentation and analysis tool. It must never modify the Omada configuration on its own.

**Core principles:**

- Omada Controller = source of technical configuration data.
- Documentation platform = collection, analysis, visualization, and explanation of that data.
- Manual additions = supplementary information stored independently of the Omada configuration.
- Documentation = an on-demand representation of the current network state.

The user interface and all explanations must be available in English. Structure the application so that additional languages, especially German, can be added later.

---

## 2. Technical Requirements

### Deployment

The application must be prepared to run on a Synology NAS.

Requirements:

- Docker / Docker Compose
- Compatible with Synology Container Manager
- ARM64 and AMD64 support, where supported by the selected libraries
- Persistent storage for all application data
- No dependency on external cloud services
- Local operation within the home network
- Configuration through environment variables and the web interface
- Container health check
- Automatic restart after NAS reboot
- Proper logging
- Backup and restore functionality

Create:

- `Dockerfile`
- `docker-compose.yml`
- `.env.example`
- `README.md` with installation instructions
- Persistent data directory
- Update and backup instructions

The application must support deployment behind an existing reverse proxy. Account for configurable base URLs and proxy headers.

### Preferred Technology Stack

**Backend**

- Python 3.12+
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic for database migrations
- HTTPX for API communication
- APScheduler for scheduled synchronization

**Frontend**

- React
- TypeScript
- Vite
- Tailwind CSS
- shadcn/ui or a comparable component framework
- React Flow for network diagrams
- Recharts for charts

**Database**

- SQLite as the default for straightforward NAS deployment
- SQLAlchemy for database access
- Architecture should allow migration to PostgreSQL later

The architecture may be adjusted if another technology is clearly better suited to the requirements. However, the application must remain lightweight and reliable on a Synology NAS.

---

## 3. Omada Controller API Integration

Implement a modular API integration for TP-Link Omada.

The application must provide the following connection settings:

- Controller IP address or hostname
- Controller port
- HTTPS / HTTP, where supported
- Client ID
- Client Secret
- API version
- Site selection
- SSL certificate verification
- Test connection function
- Display authentication status
- Timestamp of the last successful synchronization

Prefer the official Omada Open API.

**IMPORTANT:** Do not invent API endpoints or data fields. Verify the actual API documentation and implement only confirmed endpoints.

The API integration must be modular so that endpoints and API versions can be added easily later.

Credentials must be encrypted or otherwise securely protected at rest. They must never be exposed in the frontend, logs, or exported documentation.

The application requires read-only API access.

### Information to Collect

Retrieve the following information wherever it is available through the API:

**Controller**

- Model
- Firmware / software version
- Controller IP address
- Uptime and status
- Sites
- Controller information

**Network Devices**

- Routers
- Switches
- Access Points
- Model
- Device name
- MAC address
- IP address
- Firmware
- Online / offline status
- Uptime
- Adoption status
- Location
- Device relationships

**Network Configuration**

- VLANs
- LAN networks
- Subnets
- Gateways
- DHCP configuration
- DHCP ranges
- DNS servers
- WAN connections
- WAN types
- WAN VLANs
- IPv4 and IPv6 configuration
- Static routes
- VPN configurations
- NAT rules
- Port forwarding rules

**Wireless LAN**

- SSIDs
- Wireless networks
- VLAN assignment
- Frequency bands
- Security methods
- Encryption
- WLAN schedules
- Access Point assignments
- Guest network configuration
- WLAN status

WLAN passwords and PSKs must never be visible in normal documentation.

**Switch Configuration**

- Switches
- Ports
- Port numbers
- Port profiles
- VLAN assignments
- Tagged / untagged VLANs
- PoE configuration
- PoE status
- Link speed
- Duplex
- Link status
- Learned MAC addresses
- LLDP information, where available
- Port isolation

**Firewall and ACL**

- ACL rules
- Rule name
- Description
- Source
- Destination
- Protocol
- Ports
- Action: Allow / Deny
- Direction
- Status
- Order / priority
- Enabled / disabled

**Clients**

- Client name
- IP address
- MAC address
- Manufacturer
- Assigned VLAN
- Connected switch / Access Point
- Switch port, where identifiable
- Connection type
- Online / offline status
- Wi-Fi signal quality for wireless clients

Sensitive client information must be optionally anonymized in exports.

---

## 4. Backup Import as an Additional Data Source

Because not all configuration details may be available through the official API, the application must also support importing Omada backup files.

Support:

- JSON backups, where compatible with the respective Omada backup format
- Detection of controller version
- Detection of backup version
- Structured extraction of configuration data
- Validation of imported data
- Display of unsupported data areas
- Comparison between backup data and API data

Backup files must never be executed or treated as trusted input without validation.

The application must clearly identify the source of each data point:

- API
- Backup import
- Manual entry
- Derived value

If API and backup data conflict, the application must not silently overwrite one value with another. Display the conflict and identify each source and its collection timestamp.

---

## 5. Dashboard

Create a modern, easy-to-understand dashboard.

The dashboard must show at a glance:

- Number of routers
- Number of switches
- Number of Access Points
- Number of clients
- Number of VLANs
- Number of WLANs
- Number of active ACL rules
- Number of NAT rules
- Online / offline devices
- Time of last synchronization
- Detected configuration changes

Visualizations:

- Device overview
- VLAN distribution
- Client distribution
- WLAN distribution
- Device status
- Network component availability

If multiple sites exist, users must be able to switch between them.

---

## 6. Network Documentation

Create a dedicated documentation area containing complete technical documentation.

Documentation must be presented both in tables and graphically.

### 6.1 Network Overview

Display the complete network architecture:

- Internet / WAN
- Router
- Switches
- Access Points
- VLANs
- Servers
- NAS
- IoT devices
- Cameras
- DMZ
- Guest network

Show logical connections between devices.

If the actual physical cabling cannot be determined with certainty, this must be clearly indicated.

Never invent unknown connections.

### 6.2 VLAN Documentation

Create a dedicated detail page for every VLAN.

Display:

- VLAN ID
- VLAN name
- Network address
- Subnet mask
- Gateway
- DHCP range
- DNS
- Assigned devices
- Assigned SSIDs
- Assigned switch ports
- ACL rules
- Related manual documentation

Also display VLANs in a graphical network segmentation overview.

### 6.3 Device Overview

Provide a table containing all Omada devices.

Filters:

- Device type
- Model
- Location
- Status
- VLAN
- IP address

Clicking a device must open a detail page containing all available information.

### 6.4 Switch Port Documentation

Each switch must have its own port overview.

Display ports as a graphical port matrix.

Each port must include:

- Port number
- Link status
- Speed
- PoE status
- VLAN
- Port profile
- Connected device
- MAC address
- Manual port description

Color coding:

- Green: Link active
- Gray: No link
- Orange: PoE active
- Red: Error or warning
- Blue: Uplink, where positively identified

Clicking a port must open its detail page.

Manual descriptions such as “Living Room TV”, “Basement NAS”, or “Office Uplink” must be supported.

### 6.5 WLAN Documentation

Display all WLANs with:

- SSID
- VLAN
- Frequency bands
- Encryption
- Access Point assignment
- Guest network status
- Number of connected clients

Do not display passwords or PSKs.

---

## 7. ACL Analysis and Graphical Visualization

This is a particularly important area.

Develop a graphical visualization of all firewall and ACL rules.

The goal is to make it easy to understand, even without advanced networking knowledge, which network segments are allowed to communicate and which connections are blocked.

### ACL Table

Columns:

- Rule number
- Rule name
- Enabled
- Source
- Destination
- Protocol
- Port
- Action
- Direction
- Description

Filters:

- Source
- Destination
- VLAN
- Allow / Deny
- Active / inactive
- Protocol

### Graphical ACL Visualization

Create an interactive visualization using React Flow.

Display:

- VLANs as individual nodes
- Servers and important devices as nodes
- Allowed connections as green lines
- Blocked connections as red lines
- Restricted connections as orange lines
- Disabled rules as dashed lines

Clicking a connection must display the associated ACL rules.

If multiple rules exist between two networks, all relevant rules must be visible.

### ACL Explanations

Generate an understandable explanation in English for every rule.

Example:

**Technical rule:**

`IoT VLAN 30 → Home Network VLAN 10 → DENY`

**Explanation:**

“Devices in the IoT network are not allowed to establish direct connections to the home network. This helps prevent smart home devices from accessing private computers or other systems.”

Further examples:

- “The guest network is not allowed to access internal network segments.”
- “Access from the IoT network to ioBroker is explicitly allowed.”
- “Access to the management interface is restricted by this rule.”

**IMPORTANT:** Explanations must be derived from the actual rule parameters.

If a rule cannot be interpreted unambiguously because of its position, direction, or interaction with other rules, the application must flag this.

The application must not claim that a connection is allowed or blocked if the actual rule effect cannot be determined reliably.

For each rule, display:

- Technical rule
- Human-readable explanation
- Interpretation confidence
- Data source used
- Related rules

### Communication Matrix

Also create a matrix:

| Source | Destination | Communication |
|---|---|---|
| Home network | IoT | Blocked / Restricted / Allowed |
| IoT | ioBroker | Allowed |
| IoT | Home network | Blocked |
| Guest network | Home network | Blocked |

Values must be calculated from the actual ACL configuration and must never be hard-coded.

---

## 8. Manual Documentation and Additions

A central feature of the application is the ability to add custom information.

Manual information must never be lost during subsequent Omada synchronizations.

### Descriptions

The following objects must support manual descriptions:

- Sites
- VLANs
- Devices
- Switches
- Switch ports
- Access Points
- SSIDs
- ACL rules
- NAT rules
- Networks
- Servers
- Clients
- Connections
- Locations

### Example

**Automatically collected record:**

- Switch: SG2218P
- IP: 10.10.10.2
- MAC: automatically collected

**Manual additions:**

- Location: Basement network rack
- Description: Main distribution point for ground and upper floors
- Responsible party: Administration
- Note: Uplink to the second switch via port 18

### Manual Documentation Entries

Also provide freely created documentation entries.

Features:

- Title
- Description
- Category
- Related devices / VLANs / ACLs
- Tags
- Creation date
- Modification date
- Attachments
- Markdown support

Possible categories:

- Network architecture
- Security
- Cabling
- Operations
- Maintenance
- Emergency information
- Access information
- Other

Credentials and passwords must not be stored as ordinary documentation entries. If integration with a secrets manager is considered in the future, it must be implemented separately and securely.

### Important Data Model

Keep technical Omada data and manual documentation data strictly separate.

For example:

- `omada_devices`
- `omada_networks`
- `omada_acl_rules`
- `omada_switch_ports`
- `manual_descriptions`
- `manual_documents`
- `manual_relationships`
- `sync_history`
- `config_snapshots`

Synchronization must never overwrite or delete manual descriptions.

---

## 9. Full-Text Search

Implement a central search function.

Search must cover all technical and manual information.

Searchable fields:

- Device names
- IP addresses
- MAC addresses
- VLAN IDs
- VLAN names
- SSIDs
- ACL rules
- Port numbers
- Port descriptions
- Documentation text
- Tags
- Models
- Serial numbers, where available

Search results must be grouped by category.

**Example:**

Search for `192.168.30.9`

Results:

- Device: ioBroker Slave
- VLAN: IoT
- ACL rules involving this device
- Related documentation
- Related switch port information

Search must be fast and support several thousand objects.

---

## 10. Change Tracking

During every synchronization, compare the current configuration with the last stored state.

Detect:

- New devices
- Removed devices
- Changed IP addresses
- Changed VLAN assignments
- New or removed ACL rules
- Changed port profiles
- Changed WLAN configurations
- Changes to DHCP and DNS
- Changes to NAT rules

Display a change log:

| Date | Object | Change | Before | After |
|---|---|---|---|---|

Manual additions must be tracked separately in this log.

Provide a detail view for every detected change.

Users must also be able to compare any two saved configuration snapshots.

---

## 11. Automatic Synchronization

Implement configurable synchronization.

Available settings:

- Manual synchronization
- Every 5 minutes
- Every 15 minutes
- Every 30 minutes
- Hourly
- Daily

Display:

- Last successful synchronization
- Last failed synchronization
- Error details
- Number of newly collected objects
- Number of changed objects
- Synchronization duration

A failed synchronization must never corrupt the last successfully collected documentation.

Implement retry mechanisms with sensible delays and API rate limiting.

---

## 12. Documentation Export

The application must be able to generate complete documentation from the current data at any time.

Export formats:

- PDF
- DOCX
- HTML
- CSV for tables

### PDF and Word

Professional layout:

- Landscape orientation by default
- Cover page
- Table of contents
- Version information
- Creation date
- Controller information
- Network overview
- VLAN documentation
- Device overview
- Switch port documentation
- WLAN documentation
- ACL rules
- Graphical ACL communication matrix
- NAT rules
- Manual documentation
- Change overview

Diagrams must be embedded in the documents.

Users must be able to select which chapters to export.

Exports must clearly state when they were created and which data snapshot they represent.

---

## 13. User Interface

Create a modern, easy-to-use web interface.

Design requirements:

- Professional network management design
- Light and dark themes
- Responsive layout
- English language
- Sidebar navigation
- Dashboard with status cards
- Tables with sorting, filtering, and pagination
- Detail pages for all objects
- Zoomable and interactive diagrams
- Breadcrumb navigation

Main menu:

1. Dashboard
2. Network Overview
3. Devices
4. Switches and Ports
5. VLANs and Networks
6. WLAN
7. ACL / Firewall
8. NAT / Port Forwarding
9. Clients
10. Documentation
11. Search
12. Change History
13. Synchronization
14. Settings

---

## 14. Security

Security is a top priority.

- Read-only Omada API access only.
- No ability to modify Omada configurations.
- Store credentials securely using encryption.
- Never include secrets in logs.
- Never include WLAN PSKs in documentation.
- Never include API tokens in exports.
- Protection against CSRF, XSS, and SQL injection.
- Secure session management.
- Password-protected access to the web interface.
- Optional integration with reverse-proxy authentication.
- Role-based access for administrators and read-only users.
- Audit log for manual changes.
- Protection against unsafe file uploads.
- No unauthorized outbound connections.

By default, the application must only be accessible from the local network.

---

## 15. Data Quality and Transparency

Every technical record must contain the following metadata wherever available:

- Data source
- Collection timestamp
- Last update
- Site
- Controller object ID
- Data validation status

Clearly distinguish the following in the user interface:

- Retrieved directly from the controller
- Imported from backup
- Added manually
- Automatically derived
- Not available
- Unknown

If information is missing, the application must show this clearly instead of filling gaps with guessed values.

Create a data quality overview showing:

- Unassigned devices
- Unknown switch port connections
- VLANs without descriptions
- ACL rules without a reliable interpretation
- Devices without a location
- Unresolved connections
- Conflicts between data sources

---

## 16. Development and Quality Assurance

Develop the application in clearly separated modules.

Recommended implementation order:

### Phase 1 – Foundation

- Docker project
- Backend
- Frontend
- Database
- User authentication
- Configuration page
- Test Omada API connection

### Phase 2 – Data Collection

- Controller
- Sites
- Devices
- VLANs
- WLANs
- Switches and ports
- DHCP and WAN
- ACL
- NAT

### Phase 3 – Documentation

- Dashboard
- Tables
- Detail pages
- Network diagram
- ACL visualization
- Explanations

### Phase 4 – Manual Additions

- Descriptions
- Documentation entries
- Relationships
- Tags
- Attachments

### Phase 5 – Search and History

- Full-text search
- Synchronization
- Configuration comparison
- Change log

### Phase 6 – Export

- PDF
- Word
- HTML
- CSV

### Phase 7 – Stabilization

- Tests
- Error handling
- Security review
- Performance
- Synology Docker compatibility
- Backup and restore

Create automated tests for API parsers, data models, synchronization, manual additions, and exports.

Use mock data and a test mode so development can proceed without a live Omada Controller connection.

---

## 17. Implementation Requirements

Do not create only a concept or UI prototype. Build an actually runnable application.

Follow these rules:

1. First create a clear and maintainable project structure.
2. Then implement the backend and database.
3. Next implement the Omada API integration.
4. Develop the frontend as modular components.
5. Implement real data flows between backend and frontend.
6. Do not use static sample data in production views.
7. Mock data may only be used when demo mode is explicitly enabled.
8. Verify API endpoints against the official documentation.
9. Document API features that are not supported.
10. Create a complete Docker Compose configuration.
11. Verify that the application starts in a Docker environment.
12. Provide clear installation and configuration instructions.

### Acceptance Criteria

The project is considered successfully implemented only when:

- The application can be started in Synology Container Manager.
- A connection to the Omada Controller can be configured.
- Available controller data is collected automatically.
- Data is stored persistently.
- The network overview is displayed graphically.
- VLANs and devices are displayed in both tables and diagrams.
- ACL rules are explained clearly and visualized graphically.
- Manual descriptions remain stored permanently.
- Global search works.
- Changes between synchronizations are detected.
- Complete documentation can be exported as PDF and Word.
- The application remains stable when API data is unavailable.
- No sensitive credentials appear in the documentation.

---

## Final Result

A locally hosted, web-based Omada documentation platform that automatically collects the network state, explains it in understandable terms, visualizes it graphically, and combines it with manually maintained knowledge to create complete and continuously up-to-date network documentation.
