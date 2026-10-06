#!/bin/bash

prompt_required() {
    label=$1
    default=${2:-}
    while :; do
        if [ -n "$default" ]; then
            printf '%s [%s]: ' "$label" "$default" >&2
            IFS= read -r answer || exit 1
            answer=${answer:-$default}
        else
            printf '%s: ' "$label" >&2
            IFS= read -r answer || exit 1
        fi
        if [ -n "$answer" ]; then
            printf '%s' "$answer"
            return
        fi
    done
}

validate_single_line() {
    case "$1" in
        *"'"*|*'"'*|*$'\n'*|*$'\r'*) return 1 ;;
        *) return 0 ;;
    esac
}

prompt_admin_password() {
    while :; do
        printf 'Initial administrator password (at least 12 characters; input hidden): ' >&2
        IFS= read -r -s password || exit 1
        printf '\n' >&2
        if [ "${#password}" -lt 12 ] || ! validate_single_line "$password" || [[ "$password" =~ [[:space:]] ]]; then
            printf 'Use at least 12 characters without whitespace or quote characters.\n' >&2
            continue
        fi
        printf 'Confirm initial administrator password: ' >&2
        IFS= read -r -s confirmation || exit 1
        printf '\n' >&2
        if [ "$password" != "$confirmation" ]; then
            printf 'The passwords did not match; try again.\n' >&2
            continue
        fi
        printf '%s' "$password"
        return
    done
}

generate_config() {
    config_path=$1
    state_path=$2
    backup_path=$3
    forwarded_proxies=$4
    ollama_url=$5
    group_name=${6:-root}
    if [ -f "$config_path" ]; then
        info "configuration already exists; keeping $config_path"
        return
    fi

    printf '\nProduction setup needs the hotel host, its SG5 handoff URL, and the trusted admin network. No demo property is created.\n'
    while :; do
        canonical_host=$(prompt_required "Concierge hostname (DNS name only, without https://)")
        printf '%s' "$canonical_host" | grep -Eq '^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$' && \
            ! printf '%s' "$canonical_host" | grep -Eq '\.\.|(^|\.)-' && break
        info "Enter one DNS hostname, such as concierge.hotel.example."
    done
    public_url="https://${canonical_host}"

    while :; do
        antlabs_url=$(prompt_required "ANTlabs SG5 processor URL (must end with /login/main.ant)")
        case "$antlabs_url" in
            https://*|http://*)
                case "$antlabs_url" in *"/login/main.ant"* ) break ;; esac
                ;;
        esac
        info "The URL must use HTTP or HTTPS and target /login/main.ant."
    done
    while :; do
        admin_cidrs=$(prompt_required "Trusted administrator source CIDR(s), comma-separated (not 0.0.0.0/0 or ::/0)")
        case ",$admin_cidrs," in
            *,0.0.0.0/0,*|*,::/0,*|*\**|*" "*|*"'"*|*"\""*) info "Use exact trusted network ranges." ;;
            *) break ;;
        esac
    done
    admin_bootstrap_password=$(prompt_admin_password)
    if ! validate_single_line "$canonical_host" || ! validate_single_line "$antlabs_url" || ! validate_single_line "$admin_cidrs"; then
        die "Configuration values may not contain quotes or newlines."
    fi

    credential_secret=$(openssl rand -hex 32)
    metrics_token=$(openssl rand -hex 32)
    umask 027
    mkdir -p "$(dirname "$config_path")"
    {
        printf "APP_ENVIRONMENT='production'\n"
        printf "DB_PATH='%s/concierge.db'\n" "$state_path"
        printf "UPLOAD_ROOT='%s/uploads'\n" "$state_path"
        printf "CONCIERGE_BACKUP_DIR='%s'\n" "$backup_path"
        printf "DATABASE_URL=''\nREDIS_URL=''\n"
        printf "ADMIN_BOOTSTRAP_USERNAME='root'\nADMIN_BOOTSTRAP_PASSWORD='%s'\n" "$admin_bootstrap_password"
        printf "METRICS_TOKEN='%s'\n" "$metrics_token"
        printf "CANONICAL_HOSTS='%s'\nPUBLIC_BASE_URL='%s'\n" "$canonical_host" "$public_url"
        printf "ADMIN_ALLOWED_CIDRS='%s,127.0.0.1/32,::1/128'\n" "$admin_cidrs"
        printf "FORWARDED_ALLOW_IPS='%s'\n" "$forwarded_proxies"
        printf "ADMIN_COOKIE_SECURE='true'\nAPP_DEBUG='false'\n"
        printf "ALLOW_BODY_PROPERTY_SELECTION='false'\nALLOW_DEMO_SETTINGS='false'\n"
        printf "ENABLE_BACKGROUND_WORKERS='true'\n"
        printf "CREDENTIAL_ENCRYPTION_SECRET='%s'\n" "$credential_secret"
        printf "AI_PROVIDER_MODE='auto'\nAI_DEFAULT_MODE='auto'\nLOCAL_AI_ENABLED='false'\nOLLAMA_BASE_URL='%s'\n" "$ollama_url"
        printf "OLLAMA_MODEL='qwen3:8b'\nOLLAMA_THINK='false'\n"
        printf "ANTLABS_MODE='browser_handoff'\nANTLABS_AUTH_URL='%s'\nANTLABS_AUTH_METHOD='POST'\n" "$antlabs_url"
        printf "CONCIERGE_CONFIG_FILE='%s'\n" "$config_path"
    } > "$config_path"
    chmod 0640 "$config_path"
    chown "root:${group_name}" "$config_path" 2>/dev/null || chown root:wheel "$config_path"
    mkdir -p "$backup_path"
    chmod 0700 "$backup_path"
    if [ "$CONCIERGE_OS" = macos ]; then
        chown root:_concierge "$backup_path"
    fi
    printf '\nThe initial administrator password was saved in the protected configuration and was not displayed.\n\n'
}
