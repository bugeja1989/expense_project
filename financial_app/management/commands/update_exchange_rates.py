from django.core.management.base import BaseCommand, CommandError
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
import requests
import logging
from decimal import Decimal
import json
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Update currency exchange rates from external API'

    # Dictionary of supported currencies
    SUPPORTED_CURRENCIES = {
        'EUR': 'Euro',
        'USD': 'US Dollar',
        'GBP': 'British Pound',
        'JPY': 'Japanese Yen',
        'AUD': 'Australian Dollar',
        'CAD': 'Canadian Dollar',
        'CHF': 'Swiss Franc',
        'CNY': 'Chinese Yuan',
        'NZD': 'New Zealand Dollar',
        'SGD': 'Singapore Dollar'
    }

    def add_arguments(self, parser):
        parser.add_argument(
            '--provider',
            type=str,
            choices=['exchangerate-api', 'fixer', 'openexchangerates'],
            default='exchangerate-api',
            help='Exchange rate data provider'
        )
        
        parser.add_argument(
            '--base-currency',
            type=str,
            default='EUR',
            help='Base currency for rates'
        )
        
        parser.add_argument(
            '--currencies',
            nargs='+',
            help='Specific currencies to update (space-separated)'
        )
        
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force update even if rates are not stale'
        )
        
        parser.add_argument(
            '--cache-timeout',
            type=int,
            default=86400,  # 24 hours
            help='Cache timeout in seconds'
        )

    def handle(self, *args, **options):
        try:
            # Set up logging
            self.setup_logging()
            
            base_currency = options['base_currency'].upper()
            if base_currency not in self.SUPPORTED_CURRENCIES:
                raise CommandError(f"Unsupported base currency: {base_currency}")
            
            # Get currencies to update
            currencies = self.get_currencies_to_update(options['currencies'])
            
            # Check if update is needed
            if not options['force'] and not self.should_update_rates():
                self.stdout.write("Exchange rates are up to date")
                return
            
            # Get exchange rates from provider
            rates = self.fetch_exchange_rates(
                options['provider'],
                base_currency,
                currencies
            )
            
            # Store rates in cache
            self.store_rates(rates, options['cache_timeout'])
            
            # Log success
            self.stdout.write(
                self.style.SUCCESS('Successfully updated exchange rates')
            )
            
        except Exception as e:
            logger.error(f"Exchange rate update failed: {str(e)}")
            raise CommandError(f"Exchange rate update failed: {str(e)}")

    def setup_logging(self):
        """Configure logging for the command."""
        log_dir = os.path.join(settings.BASE_DIR, 'logs', 'exchange_rates')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        log_file = os.path.join(
            log_dir,
            f'exchange_rates_{timezone.now().strftime("%Y%m%d")}.log'
        )
        
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s'
        )

    def get_currencies_to_update(self, specified_currencies=None):
        """Get list of currencies to update."""
        if specified_currencies:
            # Validate specified currencies
            invalid_currencies = set(specified_currencies) - set(self.SUPPORTED_CURRENCIES.keys())
            if invalid_currencies:
                raise CommandError(f"Unsupported currencies: {', '.join(invalid_currencies)}")
            return [curr.upper() for curr in specified_currencies]
        
        return list(self.SUPPORTED_CURRENCIES.keys())

    def should_update_rates(self):
        """Check if rates should be updated."""
        last_update = cache.get('exchange_rates_last_update')
        if not last_update:
            return True
        
        # Check if last update was more than 24 hours ago
        return (timezone.now() - last_update).total_seconds() > 86400

    def fetch_exchange_rates(self, provider, base_currency, currencies):
        """Fetch exchange rates from specified provider."""
        if provider == 'exchangerate-api':
            return self.fetch_from_exchangerate_api(base_currency, currencies)
        elif provider == 'fixer':
            return self.fetch_from_fixer(base_currency, currencies)
        elif provider == 'openexchangerates':
            return self.fetch_from_openexchangerates(base_currency, currencies)
        else:
            raise CommandError(f"Unsupported provider: {provider}")

    def fetch_from_exchangerate_api(self, base_currency, currencies):
        """Fetch rates from exchangerate-api.com."""
        try:
            api_key = settings.EXCHANGERATE_API_KEY
            url = f"https://v6.exchangerate-api.com/v6/{api_key}/latest/{base_currency}"
            
            response = requests.get(url)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('result') != 'success':
                raise CommandError(f"API error: {data.get('error-type')}")
            
            rates = {}
            for currency in currencies:
                if currency != base_currency:
                    rate = data['conversion_rates'].get(currency)
                    if rate:
                        rates[currency] = Decimal(str(rate))
            
            return rates
            
        except requests.RequestException as e:
            logger.error(f"ExchangeRate API request failed: {str(e)}")
            raise

    def fetch_from_fixer(self, base_currency, currencies):
        """Fetch rates from fixer.io."""
        try:
            api_key = settings.FIXER_API_KEY
            symbols = ','.join(currencies)
            url = f"http://data.fixer.io/api/latest?access_key={api_key}&base={base_currency}&symbols={symbols}"
            
            response = requests.get(url)
            response.raise_for_status()
            
            data = response.json()
            
            if not data.get('success'):
                raise CommandError(f"API error: {data.get('error', {}).get('info')}")
            
            rates = {}
            for currency, rate in data['rates'].items():
                if currency != base_currency:
                    rates[currency] = Decimal(str(rate))
            
            return rates
            
        except requests.RequestException as e:
            logger.error(f"Fixer API request failed: {str(e)}")
            raise

    def fetch_from_openexchangerates(self, base_currency, currencies):
        """Fetch rates from openexchangerates.org."""
        try:
            api_key = settings.OPENEXCHANGERATES_API_KEY
            url = f"https://openexchangerates.org/api/latest.json?app_id={api_key}"
            
            response = requests.get(url)
            response.raise_for_status()
            
            data = response.json()
            
            # Convert rates to requested base currency
            base_rate = Decimal(str(data['rates'][base_currency]))
            rates = {}
            
            for currency in currencies:
                if currency != base_currency:
                    rate = Decimal(str(data['rates'][currency]))
                    rates[currency] = rate / base_rate
            
            return rates
            
        except requests.RequestException as e:
            logger.error(f"OpenExchangeRates API request failed: {str(e)}")
            raise

    def store_rates(self, rates, cache_timeout):
        """Store exchange rates in cache."""
        try:
            # Store rates
            cache.set('exchange_rates', rates, cache_timeout)
            
            # Store last update timestamp
            cache.set('exchange_rates_last_update', timezone.now(), cache_timeout)
            
            # Log rates to database
            self.log_rates_to_db(rates)
            
            logger.info(f"Stored exchange rates: {json.dumps(str(rates))}")
            
        except Exception as e:
            logger.error(f"Failed to store rates: {str(e)}")
            raise

    def log_rates_to_db(self, rates):
        """Log exchange rates to database for historical tracking."""
        from financial_app.models import ExchangeRate
        
        try:
            # Create exchange rate records
            for currency, rate in rates.items():
                ExchangeRate.objects.create(
                    currency=currency,
                    rate=rate,
                    date=timezone.now().date()
                )
            
        except Exception as e:
            logger.error(f"Failed to log rates to database: {str(e)}")
            raise

class ExchangeRateProvider:
    """Base class for exchange rate providers."""
    def __init__(self, api_key):
        self.api_key = api_key

    def get_rates(self, base_currency, currencies):
        raise NotImplementedError

class ExchangeRateAPIProvider(ExchangeRateProvider):
    """Provider for exchangerate-api.com."""
    def get_rates(self, base_currency, currencies):
        # Implementation
        pass

class FixerProvider(ExchangeRateProvider):
    """Provider for fixer.io."""
    def get_rates(self, base_currency, currencies):
        # Implementation
        pass

class OpenExchangeRatesProvider(ExchangeRateProvider):
    """Provider for openexchangerates.org."""
    def get_rates(self, base_currency, currencies):
        # Implementation
        pass