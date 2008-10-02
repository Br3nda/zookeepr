import hmac
import sha
import string

from zookeepr.lib.base import *
from zookeepr.lib.crud import *
from zookeepr.lib.mail import *

from zookeepr.config.lca_info import lca_info

class PaymentController(BaseController, Create, View):
    """This controller receives payment advice from CommSecure.

    the url /payment/new receives the advice
    """

    model = model.PaymentReceived
    individual = 'payment'

    def view(self):
        # hack because we don't use SecureController
        if 'signed_in_person_id' in session:
            c.signed_in_person = self.dbsession.get(model.Person, session['signed_in_person_id'])

            if c.signed_in_person != c.payment.payment_sent.invoice.person:
                redirect_to('/person/signin')

        c.person = c.payment.payment_sent.invoice.person

        return super(PaymentController, self).view()

    def new(self):
        fields = dict(request.GET)

        # FIXME: the field shoulnd't be named this, it should be
        # creation_ip.  Additionally it shouldn't only be HTTP_X_FORWARDED_FOR,
        # it should also respect REMOTE_IP if it exists -- preferring HTTP_X_...
        # though.  Typical proxy rules, etc.
        # Thirdly, this should be at the end of this validation chain so that
        # we don't have to remove it from the hmac verifyer.
        if 'HTTP_X_FORWARDED_FOR' in request.environ:
            fields['HTTP_X_FORWARDED_FOR'] = request.environ['HTTP_X_FORWARDED_FOR']

        pd = {}
        
        # these are used to match up direct one fields with the legacy fields in the db from commsecure
        for a,b in [('invoice_id', 'InvoiceID'),
                    ('payment_amount', 'Amount'),
                    ('bank_reference', 'AuthNum'),
                    ('payment_number', 'TransID'),
                    ('HTTP_X_FORWARDED_FOR', 'HTTP_X_FORWARDED_FOR')
                    ]:
            if a in fields:
                pd[b] = fields[a]

        # convert from string dollars and cents to integer cents
        # (hopefully not losing any precision, given the amounts involved)
        if 'Amount' in pd:
            pd['Amount'] = int(round(float(pd['Amount'])*100))

        pr = model.PaymentReceived(**pd)
        self.dbsession.save(pr)
        # save object now to get the id and be sure it's saved in case
        # the validation blows up
        self.dbsession.flush()

        pr.result = 'OK'
        pr.Status = 'Accepted'

        self.dbsession.flush()

        # OK we now have a valid transaction, we redirect the user to the view page
        # so they can see if their transaction was accepted or declined

        return Response("Recorded, thank you.") #only goes to SecurePay


    def _verify_hmac(self, fields):
        # do we still use/need this?

        merchantid = lca_info['commsecure_merchantid']
        secret =  lca_info['commsecure_secret']

        # Check for MAC
        if 'MAC' not in fields:
            return False

        # Generate the MAC
        keys = fields.keys()
        keys.sort()
        stringToMAC = '&'.join(['%s=%s' % (key, fields[key]) for key in keys if key != 'MAC' and key != 'HTTP_X_FORWARDED_FOR'])
        #print stringToMAC
        mac = hmac.new(secret, stringToMAC, sha).hexdigest()

        # Check the MAC
        if mac.lower() == fields['MAC'].lower():
            return True

        return False
