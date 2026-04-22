import { jsx as _jsx, Fragment as _Fragment, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from 'react';
import { APIError } from '../../api/client';
import { useSetPin, useVerifyPin, useWhoami } from '../../api/hooks';
import { PinPad } from '../../components/PinPad';
import { useParentStore } from '../../store/parent';
export function ParentGate({ children }) {
    const whoami = useWhoami();
    const isActive = useParentStore((s) => s.isActive());
    if (whoami.isLoading) {
        return (_jsx("p", { className: "text-fluid-base text-brand-700 text-center", children: "Loading\u2026" }));
    }
    if (!whoami.data)
        return null;
    if (!whoami.data.parent_pin_set) {
        return _jsx(FirstPinSetup, {});
    }
    if (isActive) {
        return _jsx(_Fragment, { children: children });
    }
    return _jsx(VerifyPin, {});
}
function FirstPinSetup() {
    const setPin = useSetPin();
    const verifyPin = useVerifyPin();
    const [stage, setStage] = useState('choose');
    const [firstPin, setFirstPin] = useState('');
    const [error, setError] = useState(null);
    const handleChoose = (pin) => {
        setFirstPin(pin);
        setStage('confirm');
        setError(null);
    };
    const handleConfirm = (pin) => {
        if (pin !== firstPin) {
            setError("PINs didn't match. Try again.");
            setStage('choose');
            setFirstPin('');
            return;
        }
        setPin.mutate({ pin }, {
            onSuccess: () => {
                verifyPin.mutate(pin);
            },
            onError: (e) => setError(e instanceof Error ? e.message : 'Failed to set PIN'),
        });
    };
    return (_jsxs("div", { className: "max-w-md mx-auto text-center space-y-6 py-8", children: [_jsx("h1", { className: "text-fluid-xl font-black text-brand-900", children: "Set a parent PIN" }), _jsx("p", { className: "text-fluid-base text-brand-700", children: "Used to unlock parent mode on this tablet. It's a soft lock to keep kids out of admin \u2014 not a security boundary." }), _jsx(PinPad, { label: stage === 'choose' ? 'Choose a 4-digit PIN' : 'Confirm PIN', onComplete: stage === 'choose' ? handleChoose : handleConfirm, disabled: setPin.isPending || verifyPin.isPending, error: error }, stage)] }));
}
function VerifyPin() {
    const verify = useVerifyPin();
    const [error, setError] = useState(null);
    return (_jsxs("div", { className: "max-w-md mx-auto text-center space-y-6 py-8", children: [_jsx("h1", { className: "text-fluid-xl font-black text-brand-900", children: "Parent mode" }), _jsx("p", { className: "text-fluid-base text-brand-700", children: "Enter PIN to continue." }), _jsx(PinPad, { onComplete: (pin) => {
                    setError(null);
                    verify.mutate(pin, {
                        onError: (e) => {
                            if (e instanceof APIError && e.errorCode === 'pin_invalid') {
                                setError('Incorrect PIN. Try again.');
                            }
                            else {
                                setError(e instanceof Error ? e.message : 'Something went wrong');
                            }
                        },
                    });
                }, disabled: verify.isPending, error: error })] }));
}
