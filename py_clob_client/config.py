from .clob_types import ContractConfig


def get_contract_config(chainID: int, neg_risk: bool = False) -> ContractConfig:
    """
    Get the contract configuration for the chain
    """

    CONFIG = {
        # Kuest contracts (Polygon mainnet)
        137: ContractConfig(
            exchange="0xaa1b8dE834E16eC69C044F5300041673C968c9eF",
            collateral="0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
            conditional_tokens="0x4682048725865bf17067bd85fF518527A262A9C7",
        ),
        # Kuest contracts (Polygon Amoy)
        80002: ContractConfig(
            exchange="0xaa1b8dE834E16eC69C044F5300041673C968c9eF",
            collateral="0x41E94Eb019C0762f9Bfcf9Fb1E58725BfB0e7582",
            conditional_tokens="0x4682048725865bf17067bd85fF518527A262A9C7",
        ),
    }

    NEG_RISK_CONFIG = {
        # Kuest NegRisk contracts (Polygon mainnet)
        137: ContractConfig(
            exchange="0xe7FA09cA716FDf498d74AFF618d32AFeacc310aB",
            collateral="0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
            conditional_tokens="0x4682048725865bf17067bd85fF518527A262A9C7",
        ),
        # Kuest NegRisk contracts (Polygon Amoy)
        80002: ContractConfig(
            exchange="0xe7FA09cA716FDf498d74AFF618d32AFeacc310aB",
            collateral="0x41E94Eb019C0762f9Bfcf9Fb1E58725BfB0e7582",
            conditional_tokens="0x4682048725865bf17067bd85fF518527A262A9C7",
        ),
    }

    if neg_risk:
        config = NEG_RISK_CONFIG.get(chainID)
    else:
        config = CONFIG.get(chainID)
    if config is None:
        raise Exception("Invalid chainID: ${}".format(chainID))

    return config
