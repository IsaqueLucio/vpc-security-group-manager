from enum import Enum


class VpcStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    ERROR = "ERROR"
    DELETED = "DELETED"

from enum import Enum


class AWSRegion(str, Enum):
    # América do Norte (EUA e Canadá)
    US_EAST_1 = "us-east-1"  # N. Virginia
    US_EAST_2 = "us-east-2"  # Ohio
    US_WEST_1 = "us-west-1"  # N. California
    US_WEST_2 = "us-west-2"  # Oregon
    CA_CENTRAL_1 = "ca-central-1"  # Canada (Central)
    CA_WEST_1 = "ca-west-1"  # Canada West (Calgary)
    MX_CENTRAL_1 = "mx-central-1"  # Mexico (Central)

    # América do Sul
    SA_EAST_1 = "sa-east-1"  # São Paulo

    # Europa
    EU_CENTRAL_1 = "eu-central-1"  # Frankfurt
    EU_CENTRAL_2 = "eu-central-2"  # Zurich
    EU_WEST_1 = "eu-west-1"  # Ireland
    EU_WEST_2 = "eu-west-2"  # London
    EU_WEST_3 = "eu-west-3"  # Paris
    EU_SOUTH_1 = "eu-south-1"  # Milan
    EU_SOUTH_2 = "eu-south-2"  # Spain
    EU_NORTH_1 = "eu-north-1"  # Stockholm

    # Ásia-Pacífico
    AP_EAST_1 = "ap-east-1"  # Hong Kong
    AP_EAST_2 = "ap-east-2"  # Taipei
    AP_SOUTH_1 = "ap-south-1"  # Mumbai
    AP_SOUTH_2 = "ap-south-2"  # Hyderabad
    AP_SOUTHEAST_1 = "ap-southeast-1"  # Singapore
    AP_SOUTHEAST_2 = "ap-southeast-2"  # Sydney
    AP_SOUTHEAST_3 = "ap-southeast-3"  # Jakarta
    AP_SOUTHEAST_4 = "ap-southeast-4"  # Melbourne
    AP_SOUTHEAST_5 = "ap-southeast-5"  # Malaysia
    AP_SOUTHEAST_7 = "ap-southeast-7"  # Thailand
    AP_NORTHEAST_1 = "ap-northeast-1"  # Tokyo
    AP_NORTHEAST_2 = "ap-northeast-2"  # Seoul
    AP_NORTHEAST_3 = "ap-northeast-3"  # Osaka
    AP_OCEANIA_1 = "ap-oceania-1"  # Auckland

    # Oriente Médio e África
    ME_SOUTH_1 = "me-south-1"  # Bahrain
    ME_CENTRAL_1 = "me-central-1"  # UAE
    ME_WEST_1 = "me-west-1"  # Tel Aviv
    AF_SOUTH_1 = "af-south-1"  # Cape Town

    # AWS GovCloud (EUA - Requer credenciais especiais)
    US_GOV_EAST_1 = "us-gov-east-1"
    US_GOV_WEST_1 = "us-gov-west-1"

    # China (Partição isolada - Requer conta local da AWS China)
    CN_NORTH_1 = "cn-north-1"  # Beijing
    CN_NORTHWEST_1 = "cn-northwest-1"  # Ningxia